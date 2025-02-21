import chainlit as cl
from typing import Dict
import json
import logging
from app.config import MCPConfig
from app.multi_client import MCPMultiClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store clients for each session
clients: Dict[str, MCPMultiClient] = {}

@cl.on_chat_start
async def start():
    try:
        config = MCPConfig.from_env()
        client = MCPMultiClient()
        status = await client.initialize_servers(config)
        
        session_id = cl.user_session.get("id")
        clients[session_id] = client
        
        # Report server status
        status_messages = []
        connected_servers = []
        
        for server_name, status in status.items():
            icon = "🚀" if "failed" not in status else "❌"
            status_messages.append(f"{icon} {server_name}: {status}")
            if "failed" not in status:
                connected_servers.append(server_name)
        
        if not connected_servers:
            await cl.Message(content="❌ No servers available. Please check configuration.").send()
            return
            
        tools_message = "\n".join(
            f"- {tool['name']}: {tool['description']}"
            for server in client.servers.values()
            if server.config.status == "connected"
            for tool in server.tools
        )
        
        await cl.Message(
            content=f"Server Status:\n{chr(10).join(status_messages)}\n\nAvailable Tools:\n{tools_message}"
        ).send()
        
    except Exception as e:
        logger.error(f"Startup error: {str(e)}", exc_info=True)
        await cl.Message(content=f"❌ Startup Error: {str(e)}").send()
        raise

@cl.on_chat_end
async def end():
    """Clean up resources when chat session ends"""
    session_id = cl.user_session.get("id")
    if session_id in clients:
        try:
            await clients[session_id].cleanup()
            logger.info(f"Cleaned up session {session_id}")
        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {str(e)}")
        finally:
            del clients[session_id]

@cl.on_message
async def main(message: cl.Message):
    """Process user messages and handle tool execution"""
    logger.info(f"Processing message: {message.content}")
    
    client = clients.get(cl.user_session.get("id"))
    if not client:
        await cl.Message(content="⚠️ Session not initialized. Please restart.").send()
        return

    try:
        async with cl.Step("Processing query...") as step:
            result = await client.process_query(message.content)
            
            # Handle tool calls first
            if result.get("tool_calls"):
                for tool_call in result["tool_calls"]:
                    server_name = tool_call["server"]
                    # Create and send a new message instead of using step.send
                    await cl.Message(
                        content=f"🔧 [{server_name}] Executing: {tool_call['name']}"
                    ).send()
                    
                    # Show args if present
                    if tool_call.get("args"):
                        await cl.Message(
                            content="📝 Arguments:",
                            elements=[
                                cl.Text(
                                    name="args",
                                    content=json.dumps(tool_call["args"], indent=2),
                                    language="json"
                                )
                            ]
                        ).send()
                    
                    # Show result
                    try:
                        result_content = tool_call["result"]
                        if isinstance(result_content, str):
                            try:
                                result_json = json.loads(result_content)
                                await cl.Message(
                                    content=f"📊 Result from {server_name}:",
                                    elements=[
                                        cl.Text(
                                            name="result",
                                            content=json.dumps(result_json, indent=2),
                                            language="json"
                                        )
                                    ]
                                ).send()
                            except json.JSONDecodeError:
                                await cl.Message(
                                    content=f"Result from {server_name}: {result_content}"
                                ).send()
                    except Exception as e:
                        await cl.Message(
                            content=f"❌ Error processing result from {server_name}: {str(e)}"
                        ).send()

            # Show final response
            if result.get("response"):
                await cl.Message(content=result["response"]).send()

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing query: {error_msg}", exc_info=True)
        await cl.Message(content=f"❌ Error: {error_msg}").send()

# @cl.on_message
# async def main(message: cl.Message):
#     """Process user messages and handle tool execution"""
#     logger.info(f"Processing message: {message.content}")
    
#     client = clients.get(cl.user_session.get("id"))
#     if not client:
#         await cl.Message(content="⚠️ Session not initialized. Please restart.").send()
#         return

#     try:
#         # Create a step and make sure to use it as a context manager
#         async with cl.Step("Processing query...") as step:
#             result = await client.process_query(message.content)
            
#             # Handle tool calls first
#             if result.get("tool_calls"):
#                 for tool_call in result["tool_calls"]:
#                     server_name = tool_call["server"]
#                     await step.send(
#                         cl.Message(content=f"🔧 [{server_name}] Executing: {tool_call['name']}")
#                     )
                    
#                     # Show args if present
#                     if tool_call.get("args"):
#                         await step.send(
#                             cl.Message(
#                                 content="📝 Arguments:",
#                                 elements=[
#                                     cl.Text(
#                                         name="args",
#                                         content=json.dumps(tool_call["args"], indent=2),
#                                         language="json"
#                                     )
#                                 ]
#                             )
#                         )
                    
#                     # Show result
#                     try:
#                         result_content = tool_call["result"]
#                         if isinstance(result_content, str):
#                             try:
#                                 result_json = json.loads(result_content)
#                                 await step.send(
#                                     cl.Message(
#                                         content=f"📊 Result from {server_name}:",
#                                         elements=[
#                                             cl.Text(
#                                                 name="result",
#                                                 content=json.dumps(result_json, indent=2),
#                                                 language="json"
#                                             )
#                                         ]
#                                     )
#                                 )
#                             except json.JSONDecodeError:
#                                 await step.send(
#                                     cl.Message(content=f"Result from {server_name}: {result_content}")
#                                 )
#                     except Exception as e:
#                         await step.send(
#                             cl.Message(content=f"❌ Error processing result from {server_name}: {str(e)}")
#                         )

#             # Show final response
#             if result.get("response"):
#                 await cl.Message(content=result["response"]).send()

#     except Exception as e:
#         error_msg = str(e)
#         logger.error(f"Error processing query: {error_msg}", exc_info=True)
#         await cl.Message(content=f"❌ Error: {error_msg}").send()


# @cl.on_message
# async def main(message: cl.Message):
#     """Process user messages and handle tool execution"""
#     logger.info(f"Processing message: {message.content}")
    
#     client = clients.get(cl.user_session.get("id"))
#     if not client:
#         await cl.Message(content="⚠️ Session not initialized. Please restart.").send()
#         return

#     try:
#         with cl.Step("Processing query..."):
#             result = await client.process_query(message.content)
            
#             # Handle tool calls first
#             if result.get("tool_calls"):
#                 for tool_call in result["tool_calls"]:
#                     server_name = tool_call["server"]
#                     await cl.Message(
#                         content=f"🔧 [{server_name}] Executing: {tool_call['name']}"
#                     ).send()
                    
#                     # Show args if present
#                     if tool_call.get("args"):
#                         await cl.Message(
#                             content="📝 Arguments:",
#                             elements=[
#                                 cl.Text(
#                                     name="args",
#                                     content=json.dumps(tool_call["args"], indent=2),
#                                     language="json"
#                                 )
#                             ]
#                         ).send()
                    
#                     # Show result
#                     try:
#                         result_content = tool_call["result"]
#                         if isinstance(result_content, str):
#                             try:
#                                 result_json = json.loads(result_content)
#                                 await cl.Message(
#                                     content=f"📊 Result from {server_name}:",
#                                     elements=[
#                                         cl.Text(
#                                             name="result",
#                                             content=json.dumps(result_json, indent=2),
#                                             language="json"
#                                         )
#                                     ]
#                                 ).send()
#                             except json.JSONDecodeError:
#                                 await cl.Message(
#                                     content=f"Result from {server_name}: {result_content}"
#                                 ).send()
#                     except Exception as e:
#                         await cl.Message(
#                             content=f"❌ Error processing result from {server_name}: {str(e)}"
#                         ).send()

#             # Show final response
#             if result.get("response"):
#                 await cl.Message(content=result["response"]).send()

#     except Exception as e:
#         error_msg = str(e)
#         logger.error(f"Error processing query: {error_msg}", exc_info=True)
#         await cl.Message(content=f"❌ Error: {error_msg}").send()


# import sys, os
# import logging
# import json
# from typing import Optional
# import chainlit as cl
# from client import MCPClient
# from app.multi_client import MCPMultiClient
# from app.config import MCPConfig

# # Configure logging
# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)


# # Store clients for each session
# clients = {}

# class ConnectionError(Exception):
#     """Raised when connection to MCP server fails"""
#     pass

# class SessionError(Exception):
#     """Raised when session-related operations fail"""
#     pass

# def get_settings() -> tuple[str, str]:
#     """Get settings from environment variables"""
#     server_path = os.getenv("MCP_SERVER_PATH")
#     db_url = os.getenv("MCP_DATABASE_URL")
    
#     if not server_path or not db_url:
#         raise ValueError(
#             "Please set MCP_SERVER_PATH and MCP_DATABASE_URL environment variables"
#         )
    
#     if not server_path.endswith('.js'):
#         raise ValueError("Server script must be a .js file")
#     if not db_url.startswith('postgresql://'):
#         raise ValueError("Database URL must start with postgresql://")
        
#     return server_path, db_url

# def validate_args() -> tuple[str, str]:
#     """Validate command line arguments"""
#     if len(sys.argv) < 3:
#         raise ValueError(
#             "Missing arguments. Usage: chainlit run app/chainlit_app.py -- "
#             "<path-to-mcp-server> <database-url>"
#         )
    
#     server_path = sys.argv[1]
#     db_url = sys.argv[2]
    
#     if not server_path.endswith('.js'):
#         raise ValueError("Server script must be a .js file")
#     if not db_url.startswith('postgresql://'):
#         raise ValueError("Database URL must start with postgresql://")
        
#     return server_path, db_url

# @cl.on_chat_start
# async def start():
#     try:
#         config = MCPConfig.from_env()
#         client = MCPMultiClient()
#         status = await client.initialize_servers(config)
        
#         session_id = cl.user_session.get("id")
#         clients[session_id] = client
        
#         # Report server status
#         status_messages = []
#         for server, status in status.items():
#             icon = "🚀" if status == "connected" else "❌"
#             status_messages.append(f"{icon} {server}: {status}")
            
#         tools_message = "\n".join(
#             f"- {tool['name']}: {tool['description']}"
#             for server in client.servers.values()
#             for tool in server.tools
#         )
        
#         await cl.Message(
#             content=f"Server Status:\n{chr(10).join(status_messages)}\n\nAvailable Tools:\n{tools_message}"
#         ).send()
        
#     except Exception as e:
#         logger.error(f"Startup error: {str(e)}", exc_info=True)
#         await cl.Message(content=f"❌ Startup Error: {str(e)}").send()
#         raise

# # @cl.on_chat_start
# # async def start():
# #     """Initialize the MCP client for this session"""
# #     try:
# #         server_path = os.getenv("MCP_SERVER_PATH")
# #         db_url = os.getenv("MCP_DATABASE_URL")
        
# #         if not server_path or not db_url:
# #             raise ValueError("Please set MCP_SERVER_PATH and MCP_DATABASE_URL environment variables")
        
# #         # Initialize client for this session
# #         client = MCPClient()
# #         tools = await client.connect_to_server(server_path, db_url)
        
# #         # Store client for this session
# #         session_id = cl.user_session.get("id")
# #         clients[session_id] = client
        
# #         await cl.Message(content=f"🚀 Connected to PostgreSQL MCP server!\n\nAvailable tools: {', '.join(tools)}").send()
        
# #     except Exception as e:
# #         logger.error(f"Startup error: {str(e)}", exc_info=True)
# #         await cl.Message(content=f"❌ Startup Error: {str(e)}").send()
# #         raise

# @cl.on_message
# async def main(message: cl.Message):
#     """Process user messages and handle tool execution"""
#     logger.info(f"Processing message: {message.content}")
    
#     client = clients.get(cl.user_session.get("id"))
#     if not client:
#         await cl.Message(content="⚠️ Session not initialized. Please restart.").send()
#         return

#     try:
#         # Process the query
#         result = await client.process_query(message.content)
        
#         # Handle tool calls first
#         if result.get("tool_calls"):
#             for tool_call in result["tool_calls"]:
#                 server_name = tool_call["server"]
#                 # Show tool execution with server name
#                 await cl.Message(
#                     content=f"🔧 [{server_name}] Executing: {tool_call['name']}"
#                 ).send()
                
#                 # Show args if present
#                 if tool_call.get("args"):
#                     await cl.Message(
#                         content="📝 Arguments:",
#                         elements=[
#                             cl.Text(
#                                 name="args",
#                                 content=json.dumps(tool_call["args"], indent=2),
#                                 language="json"
#                             )
#                         ]
#                     ).send()
                
#                 # Show result
#                 try:
#                     result_content = tool_call["result"]
#                     if isinstance(result_content, str):
#                         try:
#                             result_json = json.loads(result_content)
#                             await cl.Message(
#                                 content=f"📊 Result from {server_name}:",
#                                 elements=[
#                                     cl.Text(
#                                         name="result",
#                                         content=json.dumps(result_json, indent=2),
#                                         language="json"
#                                     )
#                                 ]
#                             ).send()
#                         except json.JSONDecodeError:
#                             await cl.Message(
#                                 content=f"Result from {server_name}: {result_content}"
#                             ).send()
#                 except Exception as e:
#                     await cl.Message(
#                         content=f"❌ Error processing result from {server_name}: {str(e)}"
#                     ).send()

#         # Show final response
#         if result.get("response"):
#             await cl.Message(content=result["response"]).send()

#     except Exception as e:
#         error_msg = str(e)
#         logger.error(f"Error processing query: {error_msg}", exc_info=True)
#         await cl.Message(content=f"❌ Error: {error_msg}").send()

# # @cl.on_message
# # async def main(message: cl.Message):
# #     """Process user messages and handle tool execution"""
# #     logger.info(f"Processing message: {message.content}")
    
# #     client = clients.get(cl.user_session.get("id"))
# #     if not client:
# #         await cl.Message(content="⚠️ Session not initialized. Please restart.").send()
# #         return

# #     try:
# #         # Process the query
# #         result = await client.process_query(message.content)
        
# #         # Handle tool calls first
# #         if result.get("tool_calls"):
# #             for tool_call in result["tool_calls"]:
# #                 # Show tool execution
# #                 await cl.Message(content=f"🔧 Executing tool: {tool_call['name']}").send()
                
# #                 # Show args if it's a SQL query
# #                 if "sql" in tool_call["args"]:
# #                     await cl.Message(
# #                         content="🔍 SQL Query:",
# #                         elements=[
# #                             cl.Text(  # Changed from cl.Code to cl.Text
# #                                 name="sql",
# #                                 content=tool_call["args"]["sql"],
# #                                 language="sql"
# #                             )
# #                         ]
# #                     ).send()
                
# #                 # Show result
# #                 try:
# #                     result_content = tool_call["result"]
# #                     if isinstance(result_content, str):
# #                         try:
# #                             result_json = json.loads(result_content)
# #                             await cl.Message(
# #                                 content="📊 Query Result:",
# #                                 elements=[
# #                                     cl.Text(  # Changed from cl.Code to cl.Text
# #                                         name="result",
# #                                         content=json.dumps(result_json, indent=2),
# #                                         language="json"
# #                                     )
# #                                 ]
# #                             ).send()
# #                         except json.JSONDecodeError:
# #                             await cl.Message(content=f"Result: {result_content}").send()
# #                 except Exception as e:
# #                     await cl.Message(content=f"❌ Error processing result: {str(e)}").send()

# #         # Show final response
# #         if result.get("response"):
# #             await cl.Message(content=result["response"]).send()

# #     except Exception as e:
# #         error_msg = str(e)
# #         logger.error(f"Error processing query: {error_msg}", exc_info=True)
# #         await cl.Message(content=f"❌ Error: {error_msg}").send()


# async def display_tool_call(tool_call: dict):
#     """Display tool call with collapsible elements"""
#     try:
#         # Display SQL query in collapsible element
#         sql = tool_call['args']['sql']
#         await cl.Message(
#             content="SQL Query:",
#             elements=[
#                 cl.Text(name="sql", content=sql, language="sql")
#             ]
#         ).send()
        
#         # Parse and display result
#         result = tool_call['result']
#         if isinstance(result, str):
#             try:
#                 result = json.loads(result)
#             except json.JSONDecodeError:
#                 pass
                
#         await cl.Message(
#             content=f"Result: {json.dumps(result, indent=2)}",
#             elements=[
#                 cl.Text(name="json", content=json.dumps(result, indent=2), language="json")
#             ]
#         ).send()
        
#     except Exception as e:
#         logger.error(f"Error displaying tool call: {e}")
#         await cl.Message(content=f"Error displaying result: {str(e)}").send()


# @cl.on_chat_end
# async def end():
#     """Clean up resources when the chat session ends"""
#     session_id = cl.user_session.get("id")
#     if client := clients.pop(session_id, None):
#         await client.cleanup()

# if __name__ == "__main__":
#     try:
#         validate_args()
#     except ValueError as e:
#         print(f"Error: {str(e)}")
#         sys.exit(1)


