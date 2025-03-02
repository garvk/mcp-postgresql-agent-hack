import logging
from typing import Dict, List, Any, Optional
from anthropic import Anthropic
from app.server_connection import ServerConnection
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ToolOrchestrator:
    """
    Orchestrates tool execution across multiple MCP servers.
    Handles tool selection, execution, and error recovery.
    """
    
    def __init__(self, servers: Dict[str, ServerConnection], anthropic_client: Anthropic):
        self.servers = servers
        self.anthropic = anthropic_client
        self.tool_name_map = {}  # Maps Claude tool names to server tool names
        self.server_map = {}     # Maps Claude tool names to server instances
        self.sequential_thinking_state = {}  # Track sequential thinking state
        
        # Build tool mappings
        self._build_tool_mappings()
    
    def _build_tool_mappings(self):
        """Build mappings between Claude tool names and server tool names"""
        for server_name, server in self.servers.items():
            if server.session and server.config.status == "connected":
                for tool in server.tools:
                    claude_name = tool["name"]
                    self.server_map[claude_name] = server
                    if hasattr(server, "tool_name_map") and claude_name in server.tool_name_map:
                        self.tool_name_map[claude_name] = server.tool_name_map[claude_name]
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get all available tools from connected servers"""
        available_tools = []
        for server in self.servers.values():
            if server.session and server.config.status == "connected":
                available_tools.extend(server.tools)
        return available_tools
    
    async def execute_tool(
        self, 
        tool_name: str, 
        tool_args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a tool on the appropriate server
        
        Args:
            tool_name: Claude tool name
            tool_args: Arguments for the tool
            
        Returns:
            Tool execution result
        """
        # Get server for this tool
        server = self.server_map.get(tool_name)
        if not server:
            error_msg = f"No server found for tool: {tool_name}"
            logger.error(error_msg)
            return {"error": error_msg, "status": "error"}
        
        # Get original tool name if needed
        actual_tool_name = self.tool_name_map.get(tool_name, tool_name)
        
        try:
            # Special handling for sequential thinking tool
            if "sequentialthinking" in tool_name.lower():
                # Check if we already have an active sequential thinking process from a different server
                active_sequential_servers = set()
                for active_tool in self.sequential_thinking_state:
                    if "sequentialthinking" in active_tool.lower():
                        active_server = self.server_map.get(active_tool)
                        if active_server and active_server.name != server.name:
                            active_sequential_servers.add(active_server.name)
                
                # If we have active sequential thinking from a different server, return an error
                if active_sequential_servers and tool_args.get("thoughtNumber", 0) == 1:
                    error_msg = f"Another sequential thinking process is already active on server(s): {', '.join(active_sequential_servers)}"
                    logger.warning(error_msg)
                    return {
                        "server": server.name,
                        "name": tool_name,
                        "args": tool_args,
                        "error": error_msg,
                        "status": "error"
                    }
                
                # Update thought number based on previous state
                if "thoughtNumber" in tool_args and "totalThoughts" in tool_args:
                    # If we have previous state, use it to update the current thought
                    if tool_name in self.sequential_thinking_state:
                        prev_state = self.sequential_thinking_state[tool_name]
                        
                        # Only increment if it's the same thought number (prevents double increments)
                        if tool_args["thoughtNumber"] == prev_state["thoughtNumber"]:
                            # Move to next thought
                            tool_args["thoughtNumber"] = prev_state["thoughtNumber"] + 1
                        elif tool_args["thoughtNumber"] <= prev_state["thoughtNumber"]:
                            # Ensure we don't go backwards
                            tool_args["thoughtNumber"] = prev_state["thoughtNumber"] + 1
                    
                    # Store current state for next call
                    self.sequential_thinking_state[tool_name] = {
                        "thoughtNumber": tool_args["thoughtNumber"],
                        "totalThoughts": tool_args["totalThoughts"]
                    }
                    
                    logger.info(f"Sequential thinking state updated: {self.sequential_thinking_state[tool_name]}")
            
            # Execute tool call on appropriate server
            logger.info(f"Executing {actual_tool_name} on server {server.name}")
            result = await server.session.call_tool(actual_tool_name, tool_args)
            logger.info(f"Tool result: {result}")
            
            # For sequential thinking, parse the result to extract metadata
            if "sequentialthinking" in tool_name.lower():
                try:
                    # Extract metadata from the result
                    result_content = result.content
                    if isinstance(result_content, list):
                        for item in result_content:
                            if hasattr(item, 'type') and item.type == "text":
                                # Parse the JSON text content
                                metadata = json.loads(item.text)
                                # Add metadata to the result
                                return {
                                    "server": server.name,
                                    "name": tool_name,
                                    "args": tool_args,
                                    "result": result.content,
                                    "metadata": metadata,
                                    "status": "success"
                                }
                except (json.JSONDecodeError, AttributeError, KeyError) as e:
                    logger.warning(f"Failed to parse sequential thinking metadata: {str(e)}")
            
            return {
                "server": server.name,
                "name": tool_name,
                "args": tool_args,
                "result": result.content,
                "status": "success"
            }
        except Exception as e:
            error_msg = f"Error executing {tool_name}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "server": server.name,
                "name": tool_name,
                "args": tool_args,
                "error": str(e),
                "status": "error"
            }
    
    async def execute_multi_step_plan(
        self, 
        messages: List[Dict[str, Any]],
        available_tools: List[Dict[str, Any]],
        system: Optional[str] = None,
        max_steps: int = 5
    ) -> Dict[str, Any]:
        """
        Execute a multi-step plan using tools
        
        Args:
            messages: Conversation history
            available_tools: Available tools
            system: System message
            max_steps: Maximum number of steps to execute
            
        Returns:
            Results of the multi-step execution
        """
        step_results = []
        final_text = []
        current_step = 0
        
        while current_step < max_steps:
            try:
                # Initial planning step
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    system=system,  # Pass system message as a separate parameter
                    messages=messages,
                    tools=available_tools
                )
                
                # Check if we're done (no tool calls)
                has_tool_call = False
                
                for content in response.content:
                    if content.type == 'text':
                        final_text.append(content.text)
                        messages.append({
                            "role": "assistant",
                            "content": content.text
                        })
                    elif content.type == 'tool_use':
                        has_tool_call = True
                        tool_name = content.name
                        tool_args = content.input
                        
                        # Execute tool
                        result = await self.execute_tool(tool_name, tool_args)
                        step_results.append(result)
                        
                        # Add tool result to conversation
                        if result["status"] == "success":
                            messages.append({
                                "role": "assistant",
                                "content": f"Using {tool_name}..."
                            })
                            messages.append({
                                "role": "user",
                                "content": result["result"]
                            })
                        else:
                            error_message = f"Error using {tool_name}: {result.get('error', 'Unknown error')}"
                            messages.append({
                                "role": "user",
                                "content": error_message
                            })
                
                # If no tool calls, we're done
                if not has_tool_call:
                    break
                    
                current_step += 1
                
            except Exception as e:
                error_msg = f"Error in step {current_step}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                final_text.append(error_msg)
                break
        
        # Get final summary if we used tools
        if step_results and current_step > 0:
            try:
                # Ask for a summary of findings
                messages.append({
                    "role": "user",
                    "content": "Please summarize your findings and insights from the analysis above."
                })
                
                summary = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    system=system,
                    messages=messages
                )
                
                if summary.content:
                    final_text.append(summary.content[0].text)
            except Exception as e:
                logger.error(f"Error getting summary: {str(e)}", exc_info=True)
        
        return {
            "response": "\n".join(final_text),
            "tool_calls": step_results,
            "steps_executed": current_step
        } 