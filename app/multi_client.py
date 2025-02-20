from typing import Dict, List, Optional, Any
from anthropic import Anthropic
from app.server_connection import ServerConnection
from app.config import MCPConfig
import logging


logger = logging.getLogger(__name__)

class MCPMultiClient:
    def __init__(self):
        self.servers: Dict[str, ServerConnection] = {}
        self.anthropic = Anthropic()
        self.conversation_history = []
        
    async def initialize_servers(self, config: MCPConfig) -> Dict[str, str]:
        """Initialize all servers and return their status"""
        status_report = {}
        
        for name, server_config in config.mcpServers.items():
            try:
                server = ServerConnection(name, server_config)
                await server.initialize()
                self.servers[name] = server
                status_report[name] = "connected"
            except Exception as e:
                logger.error(f"Failed to initialize {name}: {str(e)}")
                status_report[name] = f"failed: {str(e)}"
                
        return status_report


    
    async def process_query(self, query: str) -> Dict[str, Any]:
        """Process query using Claude and available tools across all servers"""
        logger.info("Starting process_query")
        final_text = []
        tool_calls = []
        
        # Build initial messages with conversation history
        messages = self.conversation_history + [{"role": "user", "content": query}]
        
        # Collect all available tools from connected servers
        available_tools = []
        for server in self.servers.values():
            if server.session and server.config.status == "connected":
                available_tools.extend(server.tools)

        try:
            # Initial Claude API call
            logger.info(f"Available tools: {[tool['name'] for tool in available_tools]}")
            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=messages,
                tools=available_tools
            )

            logger.info(f"Got response from Claude with {len(response.content)} content items")
            for content in response.content:
                logger.info(f"Processing content type: {content.type}")
                if content.type == 'text':
                    final_text.append(content.text)
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": content.text
                    })
                elif content.type == 'tool_use':
                    tool_name = content.name
                    tool_args = content.input
                    
                    # Parse server name from tool name (e.g., "weather_get_forecast")
                    parts = tool_name.split('_', 1)
                    if len(parts) != 2:
                        error_msg = f"Invalid tool name format: {tool_name}. Expected format: server_toolname"
                        final_text.append(error_msg)
                        continue
                        
                    server_name, _ = parts
                    server = self.servers.get(server_name)
                    
                    if not server or server.config.status != "connected":
                        error_msg = f"🔴 Server '{server_name}' is not available"
                        final_text.append(error_msg)
                        continue

                    # Get original tool name
                    actual_tool_name = server.tool_name_map.get(tool_name)
                    if not actual_tool_name:
                        error_msg = f"🔴 Tool '{tool_name}' not found"
                        final_text.append(error_msg)
                        continue

                    try:
                        # Execute tool call on appropriate server
                        result = await server.session.call_tool(actual_tool_name, tool_args)
                        
                        # Record tool call
                        tool_call = {
                            "server": server_name,
                            "name": tool_name,
                            "args": tool_args,
                            "result": result.content
                        }
                        tool_calls.append(tool_call)

                        # Update conversation history
                        self.conversation_history.extend([
                            {"role": "assistant", "content": f"Using {tool_name}..."},
                            {"role": "user", "content": result.content}
                        ])

                        # Get follow-up response from Claude
                        follow_up = self.anthropic.messages.create(
                            model="claude-3-5-sonnet-20241022",
                            max_tokens=1000,
                            messages=self.conversation_history,
                            tools=available_tools
                        )
                        
                        follow_up_text = follow_up.content[0].text
                        final_text.append(follow_up_text)
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": follow_up_text
                        })

                    except Exception as e:
                        error_msg = f"🔴 Error executing {tool_name}: {str(e)}"
                        final_text.append(error_msg)
                        logger.error(error_msg, exc_info=True)

            # Trim conversation history if it gets too long
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]

            return {
                "response": "\n".join(final_text),
                "tool_calls": tool_calls
            }

        except Exception as e:
            logger.error(f"Error in process_query: {str(e)}", exc_info=True)
            raise

    # async def process_query(self, query: str) -> Dict[str, Any]:
    #     """Process query using Claude and available tools across all servers"""
    #     final_text = []
    #     tool_calls = []
        
    #     # Build initial messages with conversation history
    #     messages = self.conversation_history + [{"role": "user", "content": query}]
        
    #     # Collect all available tools from connected servers
    #     available_tools = []
    #     for server in self.servers.values():
    #         if server.session and server.config.status == "connected":
    #             available_tools.extend(server.tools)

    #     try:
    #         # Initial Claude API call
    #         response = self.anthropic.messages.create(
    #             model="claude-3-5-sonnet-20241022",
    #             max_tokens=1000,
    #             messages=messages,
    #             tools=available_tools
    #         )

    #         for content in response.content:
    #             if content.type == 'text':
    #                 final_text.append(content.text)
    #                 self.conversation_history.append({
    #                     "role": "assistant",
    #                     "content": content.text
    #                 })
    #             elif content.type == 'tool_use':
    #                 tool_name = content.name
    #                 tool_args = content.input
                    
    #                 # Parse server name from tool name (e.g., "weather.get_forecast")
    #                 try:
    #                     server_name, actual_tool_name = tool_name.split('.', 1)
    #                 except ValueError:
    #                     error_msg = f"Invalid tool name format: {tool_name}. Expected format: server.tool_name"
    #                     final_text.append(error_msg)
    #                     continue

    #                 server = self.servers.get(server_name)
    #                 if not server or server.config.status != "connected":
    #                     error_msg = f"🔴 Server '{server_name}' is not available"
    #                     final_text.append(error_msg)
    #                     continue

    #                 try:
    #                     # Execute tool call on appropriate server
    #                     result = await server.session.call_tool(actual_tool_name, tool_args)
                        
    #                     # Record tool call
    #                     tool_call = {
    #                         "server": server_name,
    #                         "name": tool_name,
    #                         "args": tool_args,
    #                         "result": result.content
    #                     }
    #                     tool_calls.append(tool_call)

    #                     # Update conversation history
    #                     self.conversation_history.extend([
    #                         {"role": "assistant", "content": f"Using {tool_name}..."},
    #                         {"role": "user", "content": result.content}
    #                     ])

    #                     # Get follow-up response from Claude
    #                     follow_up = self.anthropic.messages.create(
    #                         model="claude-3-5-sonnet-20241022",
    #                         max_tokens=1000,
    #                         messages=self.conversation_history,
    #                         tools=available_tools
    #                     )
                        
    #                     follow_up_text = follow_up.content[0].text
    #                     final_text.append(follow_up_text)
    #                     self.conversation_history.append({
    #                         "role": "assistant",
    #                         "content": follow_up_text
    #                     })

    #                 except Exception as e:
    #                     error_msg = f"🔴 Error executing {tool_name}: {str(e)}"
    #                     final_text.append(error_msg)
    #                     logger.error(error_msg, exc_info=True)

    #         # Trim conversation history if it gets too long
    #         if len(self.conversation_history) > 10:
    #             self.conversation_history = self.conversation_history[-10:]

    #         return {
    #             "response": "\n".join(final_text),
    #             "tool_calls": tool_calls
    #         }

    #     except Exception as e:
    #         logger.error(f"Error in process_query: {str(e)}", exc_info=True)
    #         raise

    

    # async def process_query(self, query: str) -> Dict[str, any]:
    #     """Process query using Claude and available tools across all servers"""
    #     messages = [{"role": "user", "content": query}]
    #     tool_calls = []
    #     final_text = []
        
    #     # Collect all available tools from connected servers
    #     available_tools = []
    #     for server_name, server in self.servers.items():
    #         if server.session and server.tools:
    #             available_tools.extend(server.tools)

    #     try:
    #         # Initial Claude API call
    #         response = self.anthropic.messages.create(
    #             model="claude-3-5-sonnet-20241022",
    #             max_tokens=1000,
    #             messages=messages,
    #             tools=available_tools
    #         )

    #         for content in response.content:
    #             if content.type == 'text':
    #                 final_text.append(content.text)
    #             elif content.type == 'tool_use':
    #                 tool_name = content.name
    #                 tool_args = content.input
                    
    #                 # Extract server name from namespaced tool
    #                 server_name, actual_tool_name = tool_name.split('.', 1)
    #                 server = self.servers.get(server_name)
                    
    #                 if not server or server.config.status != "connected":
    #                     error_msg = f"Server {server_name} is not available"
    #                     final_text.append(error_msg)
    #                     continue

    #                 try:
    #                     # Execute tool call on appropriate server
    #                     result = await server.session.call_tool(actual_tool_name, tool_args)
    #                     tool_calls.append({
    #                         "name": tool_name,
    #                         "args": tool_args,
    #                         "result": result.content,
    #                         "server": server_name
    #                     })

    #                     # Continue conversation with tool results
    #                     messages.extend([
    #                         {"role": "assistant", "content": f"Using {tool_name}..."},
    #                         {"role": "user", "content": result.content}
    #                     ])

    #                     # Get follow-up response from Claude
    #                     follow_up = self.anthropic.messages.create(
    #                         model="claude-3-5-sonnet-20241022",
    #                         max_tokens=1000,
    #                         messages=messages
    #                     )
    #                     final_text.append(follow_up.content[0].text)

    #                 except Exception as e:
    #                     error_msg = f"Error executing {tool_name}: {str(e)}"
    #                     final_text.append(error_msg)
    #                     logger.error(error_msg)

    #         return {
    #             "response": "\n".join(final_text),
    #             "tool_calls": tool_calls
    #         }

    #     except Exception as e:
    #         logger.error(f"Error in process_query: {str(e)}", exc_info=True)
    #         raise

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
        