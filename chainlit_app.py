import chainlit as cl
from typing import Dict
import json
import logging
from app.config import MCPConfig
from app.chainlit_client import ChainlitMCPClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store clients for each session
clients: Dict[str, ChainlitMCPClient] = {}

@cl.on_chat_start
async def start():
    try:
        config = MCPConfig.from_env()
        client = ChainlitMCPClient()
        status = await client.initialize_servers(config)
        
        session_id = cl.user_session.get("id")
        clients[session_id] = client
        
        # Report server status and available tools
        status_messages = []
        tools_available = []
        
        for server_name, status in status.items():
            icon = "🟢" if status == "connected" else "🔴"
            status_messages.append(f"{icon} {server_name}: {status}")
            
            # Add available tools for connected servers
            if status == "connected":
                server = client.servers[server_name]
                for tool in server.tools:
                    tools_available.append(f"- {tool['name']}: {tool['description']}")
        
        status_text = "Server Status:\n" + "\n".join(status_messages)
        tools_text = "\nAvailable Tools:\n" + "\n".join(tools_available)
        
        await cl.Message(content=f"{status_text}{tools_text}").send()
        
    except Exception as e:
        logger.error(f"Startup error: {str(e)}", exc_info=True)
        await cl.Message(content=f"❌ Startup Error: {str(e)}").send()
        raise

@cl.on_chat_end
async def end():
    """Clean up when chat ends"""
    session_id = cl.user_session.get("id")
    if session_id in clients:
        await clients[session_id].cleanup()
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
        # Using the new process_query_with_ui method
        result = await client.process_query_with_ui(message.content)
        
    except Exception as e:
        error_msg = f"Error processing query: {str(e)}"
        logger.error(error_msg, exc_info=True)
        await cl.Message(content=f"❌ {error_msg}").send()


