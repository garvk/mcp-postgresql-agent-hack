import logging
import json
from typing import Dict, List, Any, Optional
from anthropic import Anthropic

from app.config import MCPConfig
from app.server_connection import ServerConnection
from app.orchestration.prompt_manager import PromptManager
from app.orchestration.tool_orchestrator import ToolOrchestrator
from app.orchestration.conversation_manager import ConversationManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Orchestrator:
    """
    Main orchestration layer for MCP tool interactions.
    Coordinates prompt generation, tool execution, and conversation management.
    """
    
    def __init__(self):
        self.anthropic = Anthropic()
        self.servers = {}
        self.prompt_manager = PromptManager()
        self.conversation_manager = ConversationManager()
        self.tool_orchestrator = None  # Will be initialized after servers
    
    async def initialize_servers(self, config: MCPConfig) -> Dict[str, str]:
        """Initialize connections to MCP servers and load schema information"""
        status = {}
        schema_info = {}
        
        for server_name, server_config in config.mcpServers.items():
            try:
                server = ServerConnection(server_name, server_config)
                await server.initialize()
                
                self.servers[server_name] = server
                status[server_name] = f"Connected with {len(server.tools)} tools"
                server_config.status = "connected"
                
                # Load schema information for PostgreSQL servers
                if "postgres" in server_name.lower() or any("query" in tool["name"] for tool in server.tools):
                    schema_info[server_name] = await self._load_postgres_schema(server)
                
            except Exception as e:
                error_msg = f"Failed to connect: {str(e)}"
                logger.error(f"Error initializing server {server_name}: {error_msg}", exc_info=True)
                status[server_name] = error_msg
                server_config.status = "failed"
        
        # Initialize tool orchestrator with connected servers
        self.tool_orchestrator = ToolOrchestrator(self.servers, self.anthropic)
        
        # Set up system prompt with available tools and schema information
        available_tools = self.tool_orchestrator.get_available_tools()
        
        # Use the enhanced Shopify prompt with schema information
        system_prompt = self.prompt_manager.generate_shopify_prompt(
            tools=available_tools,
            schema_info=schema_info if schema_info else None
        )
        
        logger.info(f"System prompt: {system_prompt}")
        self.conversation_manager.set_system_message(system_prompt)
        
        return status
    
    async def _load_postgres_schema(self, server: ServerConnection) -> Dict[str, Any]:
        """Load schema information from a PostgreSQL server"""
        schema_info = {}
        
        try:
            # Get list of resources (tables)
            resources_response = await server.session.list_resources()
            
            # Load schema for each table
            for resource in resources_response.resources:
                # Convert AnyUrl to string before checking
                uri_str = str(resource.uri)
                if "/schema" in uri_str:
                    # Extract table name from URI
                    table_name = uri_str.split('/')[-2]
                    contents = await server.session.read_resource(resource.uri)
                    if contents and contents.contents:
                        schema_info[table_name] = json.loads(contents.contents[0].text)
            
            logger.info(f"Loaded schema information for {len(schema_info)} tables from {server.name}")
            return schema_info
        except Exception as e:
            logger.error(f"Error loading schema from {server.name}: {str(e)}", exc_info=True)
            return {}
    
    async def process_query(self, query: str, multi_step: bool = True) -> Dict[str, Any]:
        """
        Process a user query using available tools
        
        Args:
            query: User query
            multi_step: Whether to use multi-step reasoning
            
        Returns:
            Processing results including response text and tool calls
        """
        logger.info(f"Processing query: {query}")
        
        # Add user query to conversation history
        self.conversation_manager.add_user_message(query)
        
        # Get available tools
        available_tools = self.tool_orchestrator.get_available_tools()
        if not available_tools:
            return {
                "response": "No tools are available. Please check server connections.",
                "tool_calls": [],
                "status": "error"
            }
        
        try:
            if multi_step:
                # Use multi-step reasoning approach
                result = await self.tool_orchestrator.execute_multi_step_plan(
                    messages=self.conversation_manager.get_messages(),
                    available_tools=available_tools,
                    system=self.conversation_manager.get_system_message()
                )
                logger.info(f"Multi-step execution result: {result}")
            else:
                # Use single response approach with recursive tool handling
                messages = self.conversation_manager.get_messages()
                system = self.conversation_manager.get_system_message()
                
                # Initial Claude API call
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    system=system,
                    messages=messages,
                    tools=available_tools
                )
                logger.info(f"Initial Claude response: {response}")
                
                # Process response with recursive tool handling
                result = await self._process_response_with_tools(
                    response=response,
                    available_tools=available_tools,
                    system=system,
                    max_steps=10,  # Set a reasonable limit for nested tool calls
                    current_step=0,
                    tool_calls=[]
                )
            
            return result
            
        except Exception as e:
            error_msg = f"Error processing query: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "response": error_msg,
                "tool_calls": [],
                "status": "error"
            }
    
    async def _process_response_with_tools(
        self, 
        response, 
        available_tools: List[Dict[str, Any]],
        system: str,
        max_steps: int = 5,
        current_step: int = 0,
        tool_calls: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process a Claude response, handling any tool calls recursively
        
        Args:
            response: Claude API response
            available_tools: Available tools
            system: System message
            max_steps: Maximum number of steps to execute
            current_step: Current step count
            tool_calls: List to accumulate tool calls
            
        Returns:
            Processing results
        """
        if tool_calls is None:
            tool_calls = []
        
        final_text = []
        has_tool_call = False
        
        # Check if we've reached the maximum steps
        if current_step >= max_steps:
            final_text.append("Reached maximum number of tool execution steps.")
            return {
                "response": "\n".join(final_text),
                "tool_calls": tool_calls,
                "status": "success",
                "steps_executed": current_step
            }
        
        # Process each content item in the response
        for content in response.content:
            if content.type == 'text':
                final_text.append(content.text)
                self.conversation_manager.add_assistant_message(content.text)
            elif content.type == 'tool_use':
                has_tool_call = True
                tool_name = content.name
                tool_args = content.input
                
                # Execute tool
                result = await self.tool_orchestrator.execute_tool(tool_name, tool_args)
                tool_calls.append(result)
                
                # Add tool result to conversation
                if result["status"] == "success":
                    self.conversation_manager.add_tool_result(tool_name, result["result"])
                    
                    # Get follow-up response
                    follow_up = self.anthropic.messages.create(
                        model="claude-3-5-sonnet-20241022",
                        max_tokens=1000,
                        system=system,
                        messages=self.conversation_manager.get_messages(),
                        tools=available_tools
                    )
                    logger.info(f"Follow-up Claude response: {follow_up}")
                    
                    # Recursively process the follow-up response
                    nested_result = await self._process_response_with_tools(
                        response=follow_up,
                        available_tools=available_tools,
                        system=system,
                        max_steps=max_steps,
                        current_step=current_step + 1,
                        tool_calls=tool_calls
                    )
                    
                    # Add the nested response text to our final text
                    if "response" in nested_result:
                        final_text.append(nested_result["response"])
                else:
                    error_message = f"Error using {tool_name}: {result.get('error', 'Unknown error')}"
                    final_text.append(error_message)
                    self.conversation_manager.add_assistant_message(error_message)
            else:
                # Handle any other unknown content types
                final_text.append(f"Received unsupported content type: {content.type}")
                logger.warning(f"Unsupported content type in response: {content.type}")
        
        # Return the final result
        return {
            "response": "\n".join(final_text),
            "tool_calls": tool_calls,
            "status": "success",
            "steps_executed": current_step + (1 if has_tool_call else 0)
        }
    
    async def cleanup(self):
        """Clean up all server connections"""
        cleanup_errors = []
        
        for server_name, server in self.servers.items():
            try:
                await server.exit_stack.aclose()
                logger.info(f"Successfully cleaned up server: {server_name}")
            except Exception as e:
                error_msg = f"Error cleaning up server {server_name}: {str(e)}"
                cleanup_errors.append(error_msg)
                logger.error(error_msg, exc_info=True)
        
        if cleanup_errors:
            raise Exception("\n".join(cleanup_errors))
    
    async def generate_summary(self, result: Dict[str, Any]) -> str:
        """
        Generate a concise summary of the results and tool calls
        
        Args:
            result: The result dictionary from process_query
            
        Returns:
            A concise summary of the findings
        """
        try:
            # Create a prompt for summarization
            tool_calls_info = []
            for tool_call in result.get("tool_calls", []):
                tool_name = tool_call.get("name", "unknown")
                status = tool_call.get("status", "unknown")
                if status == "success":
                    tool_calls_info.append(f"Used {tool_name} successfully")
                else:
                    tool_calls_info.append(f"Attempted to use {tool_name} but encountered an error")
            
            tool_calls_text = "\n".join(tool_calls_info)
            detailed_response = result.get("response", "")
            
            # Add a summarization request to the conversation
            self.conversation_manager.add_user_message(
                f"Please provide a summary of the key findings, insights, recommendations, and actions from the analysis above. "
                f"Focus on the most important information for the user, dont be too verbose and careful not hide important information such as numbers, dates, etc."
            )
            
            # Get the summary from Claude
            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1100,  # Short summary
                system=self.conversation_manager.get_system_message(),
                messages=self.conversation_manager.get_messages()
            )
            
            # Extract the summary text
            summary = ""
            for content in response.content:
                if content.type == 'text':
                    summary = content.text
                    break
            
            # Remove the summarization request from conversation history to keep it clean
            if self.conversation_manager.conversation_history:
                self.conversation_manager.conversation_history.pop()
            
            return summary
        
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}", exc_info=True)
            return "Unable to generate summary due to an error." 