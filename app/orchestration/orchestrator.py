import logging
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
        """
        Initialize connections to MCP servers
        
        Args:
            config: MCP server configuration
            
        Returns:
            Dictionary of server names to status messages
        """
        status = {}
        
        for server_name, server_config in config.mcpServers.items():
            try:
                server = ServerConnection(server_name, server_config)
                await server.initialize()
                
                self.servers[server_name] = server
                status[server_name] = f"Connected with {len(server.tools)} tools"
                server_config.status = "connected"
                
            except Exception as e:
                error_msg = f"Failed to connect: {str(e)}"
                logger.error(f"Error initializing server {server_name}: {error_msg}", exc_info=True)
                status[server_name] = error_msg
                server_config.status = "failed"
        
        # Initialize tool orchestrator with connected servers
        self.tool_orchestrator = ToolOrchestrator(self.servers, self.anthropic)
        
        # Set up system prompt with available tools
        available_tools = self.tool_orchestrator.get_available_tools()
        system_prompt = self.prompt_manager.generate_system_prompt(available_tools)
        self.conversation_manager.set_system_message(system_prompt)
        
        return status
    
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
                # Use single response approach
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
                
                final_text = []
                tool_calls = []
                
                for content in response.content:
                    if content.type == 'text':
                        final_text.append(content.text)
                        self.conversation_manager.add_assistant_message(content.text)
                    elif content.type == 'tool_use':
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
                            # logger.info(f"Follow-up content: {follow_up.content}")
                            
                            # Handle different content types in follow-up
                            for follow_content in follow_up.content:
                                if follow_content.type == 'text':
                                    final_text.append(follow_content.text)
                                    self.conversation_manager.add_assistant_message(follow_content.text)
                                elif follow_content.type == 'tool_use':
                                    # Handle nested tool use (uncommon but possible)
                                    nested_tool_name = follow_content.name
                                    nested_tool_args = follow_content.input
                                    final_text.append(f"Note: Claude attempted to use another tool ({nested_tool_name}) in follow-up.")
                                else:
                                    # Handle any other unknown content types
                                    final_text.append(f"Received unsupported content type: {follow_content.type}")
                                    logger.warning(f"Unsupported content type in follow-up: {follow_content.type}")
                        else:
                            error_message = f"Error using {tool_name}: {result.get('error', 'Unknown error')}"
                            final_text.append(error_message)
                    else:
                        # Handle any other unknown content types
                        final_text.append(f"Received unsupported content type: {content.type}")
                        logger.warning(f"Unsupported content type in response: {content.type}")
                
                result = {
                    "response": "\n".join(final_text),
                    "tool_calls": tool_calls,
                    "status": "success"
                }
            
            return result
            
        except Exception as e:
            error_msg = f"Error processing query: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "response": error_msg,
                "tool_calls": [],
                "status": "error"
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