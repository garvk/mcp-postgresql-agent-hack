import chainlit as cl
from typing import Dict
import json
import logging
import os
from app.config import MCPConfig
from app.orchestration.orchestrator import Orchestrator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store orchestrators for each session
orchestrators: Dict[str, Orchestrator] = {}

@cl.on_chat_start
async def start():
    try:
        config = MCPConfig.from_env()
        orchestrator = Orchestrator()
        status = await orchestrator.initialize_servers(config)
        
        session_id = cl.user_session.get("id")
        orchestrators[session_id] = orchestrator
        
        # Report server status
        status_messages = []
        connected_servers = []
        
        for server_name, status_msg in status.items():
            icon = "🚀" if "failed" not in status_msg else "❌"
            status_messages.append(f"{icon} {server_name}: {status_msg}")
            if "failed" not in status_msg:
                connected_servers.append(server_name)
        
        if not connected_servers:
            await cl.Message(content="❌ No servers available. Please check configuration.").send()
            return
            
        tools_message = "\n".join(
            f"- {tool['name']}: {tool['description']}"
            for server in orchestrator.servers.values()
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

@cl.on_message
async def main(message: cl.Message):
    """Process user messages and handle tool execution"""
    logger.info(f"Processing message: {message.content}")
    
    orchestrator = orchestrators.get(cl.user_session.get("id"))
    if not orchestrator:
        await cl.Message(content="⚠️ Session not initialized. Please restart.").send()
        return
    
    try:
        # Check for multi-step flag
        multi_step = "multi-step" in message.content.lower() or "multistep" in message.content.lower()
        
        async with cl.Step("Processing query...") as step:
            # Process the query with our orchestrator
            result = await orchestrator.process_query(message.content, multi_step=multi_step)
            
            # Handle tool calls
            if result.get("tool_calls"):
                for tool_call in result["tool_calls"]:
                    server_name = tool_call.get("server", "unknown")
                    tool_name = tool_call.get("name", "unknown")
                    
                    # Create and send a new message for the tool execution
                    await cl.Message(
                        content=f"🔧 [{server_name}] Executing: {tool_name}"
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
                    
                    # Show result or error
                    if tool_call.get("status") == "error":
                        await cl.Message(
                            content=f"❌ Error: {tool_call.get('error', 'Unknown error')}"
                        ).send()
                    else:
                        result_content = tool_call.get("result", "")
                        try:
                            # Try to parse as JSON for better display
                            json_result = json.loads(result_content)
                            await cl.Message(
                                content="✅ Result:",
                                elements=[
                                    cl.Text(
                                        name="result",
                                        content=json.dumps(json_result, indent=2),
                                        language="json"
                                    )
                                ]
                            ).send()
                        except (json.JSONDecodeError, TypeError):
                            # Not JSON, send as plain text
                            await cl.Message(
                                content=f"✅ Result: {result_content}"
                            ).send()
            
            # Send the final response
            await cl.Message(content=result.get("response", "")).send()
            
            # If multi-step, show step count
            if multi_step and "steps_executed" in result:
                await cl.Message(
                    content=f"🔄 Executed {result['steps_executed']} reasoning steps."
                ).send()
                
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}", exc_info=True)
        await cl.Message(content=f"❌ Error: {str(e)}").send()

@cl.on_chat_end
async def end():
    """Clean up resources when chat ends"""
    session_id = cl.user_session.get("id")
    orchestrator = orchestrators.pop(session_id, None)
    
    if orchestrator:
        try:
            await orchestrator.cleanup()
            logger.info(f"Cleaned up resources for session {session_id}")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}", exc_info=True) 