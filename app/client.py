# import asyncio
# from typing import Optional, List, Dict
# from contextlib import AsyncExitStack

# from mcp import ClientSession, StdioServerParameters
# from mcp.client.stdio import stdio_client

# from anthropic import Anthropic
# from dotenv import load_dotenv
# import logging
# logger = logging.getLogger(__name__)

# load_dotenv()

# class MCPClient:

#     def __init__(self):
#         logger.debug("Initializing MCPClient")
#         self.session: Optional[ClientSession] = None
#         self.exit_stack = AsyncExitStack()
#         self.anthropic = Anthropic()
#         self.tools: List[Dict] = []

#     async def connect_to_server(self, server_script_path: str, database_url: str) -> List[str]:
#         """Connect to an MCP server and return available tools
        
#         Args:
#             server_script_path: Path to the server script (.js)
#             database_url: PostgreSQL database URL
            
#         Returns:
#             List of available tool names
#         """
#         if not server_script_path.endswith('.js'):
#             raise ValueError("Server script must be a .js file")
            
#         server_params = StdioServerParameters(
#             command="node",
#             args=[server_script_path, database_url],
#             env=None
#         )
        
#         try:
#             stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
#             self.stdio, self.write = stdio_transport
#             self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
            
#             await self.session.initialize()
            
#             # List and store available tools
#             response = await self.session.list_tools()
#             self.tools = [{ 
#                 "name": tool.name,
#                 "description": tool.description,
#                 "input_schema": tool.inputSchema
#             } for tool in response.tools]
            
#             return [tool["name"] for tool in self.tools]
            
#         except Exception as e:
#             await self.cleanup()
#             raise ConnectionError(f"Failed to connect to MCP server: {str(e)}")

#     async def process_query(self, query: str) -> Dict[str, any]:
#         """Process a query using Claude and available tools"""
#         messages = [{"role": "user", "content": query}]
#         tool_calls = []
#         final_text = []

#         try:
#             # Get available tools
#             response = await self.session.list_tools()
#             available_tools = [{ 
#                 "name": tool.name,
#                 "description": tool.description,
#                 "input_schema": tool.inputSchema
#             } for tool in response.tools]

#             # Initial Claude API call
#             response = self.anthropic.messages.create(
#                 model="claude-3-5-sonnet-20241022",
#                 max_tokens=1000,
#                 messages=messages,
#                 tools=available_tools
#             )

#             for content in response.content:
#                 if content.type == 'text':
#                     final_text.append(content.text)
#                 elif content.type == 'tool_use':
#                     try:
#                         tool_name = content.name
#                         tool_args = content.input
                        
#                         # Execute tool call and store result
#                         result = await self.session.call_tool(tool_name, tool_args)
#                         tool_calls.append({
#                             "name": tool_name,
#                             "args": tool_args,
#                             "result": result.content
#                         })

#                         # Add tool response to messages for context
#                         messages.append({
#                             "role": "assistant",
#                             "content": f"Tool {tool_name} result: {result.content}"
#                         })

#                         # Get follow-up response from Claude
#                         follow_up = self.anthropic.messages.create(
#                             model="claude-3-5-sonnet-20241022",
#                             max_tokens=1000,
#                             messages=messages
#                         )
#                         final_text.append(follow_up.content[0].text)

#                     except Exception as e:
#                         error_msg = f"Error executing tool {tool_name}: {str(e)}"
#                         final_text.append(error_msg)
#                         logger.error(error_msg)

#             return {
#                 "response": "\n".join(final_text),
#                 "tool_calls": tool_calls
#             }

#         except Exception as e:
#             logger.error(f"Error in process_query: {str(e)}", exc_info=True)
#             raise

#     async def cleanup(self):
#         """Clean up resources properly"""
#         if self.exit_stack:
#             try:
#                 await self.exit_stack.aclose()
#             except Exception as e:
#                 print(f"Error during cleanup: {str(e)}")
#             finally:
#                 self.session = None
#                 self.tools = []

