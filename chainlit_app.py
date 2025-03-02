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
        # multi-step is not fully supported yet; it aims to support advanced planning before query execution
        # Check for multi-step flag; multi-step is not fully supported yet
        multi_step = "multi-step" in message.content.lower() or "multistep" in message.content.lower()
        
        async with cl.Step("Processing query...") as step:
            # Process the query with our orchestrator
            result = await orchestrator.process_query(message.content, multi_step=multi_step)
            logger.info(f"Result from orchestrator: {result}")
            
            # Handle tool calls
            if result.get("tool_calls"):
                sequential_thinking_progress = {}
                active_sequential_server = None  # Track which server is handling sequential thinking
                skip_next = False
                
                for i, tool_call in enumerate(result["tool_calls"]):
                    # Skip if marked by previous iteration
                    if skip_next:
                        skip_next = False
                        continue
                        
                    server_name = tool_call.get("server", "unknown")
                    tool_name = tool_call.get("name", "unknown")
                    
                    # Special handling for sequential thinking
                    if "sequentialthinking" in tool_name.lower():
                        # If we have an active sequential thinking server and it's different, log a warning
                        if active_sequential_server and active_sequential_server != server_name:
                            logger.warning(f"Multiple sequential thinking servers detected: {active_sequential_server} and {server_name}")
                        
                        # Set the active sequential thinking server if not already set
                        if not active_sequential_server:
                            active_sequential_server = server_name
                        
                        # Track sequential thinking progress
                        thought_num = tool_call.get("args", {}).get("thoughtNumber", 0)
                        total_thoughts = tool_call.get("args", {}).get("totalThoughts", 0)
                        thought_text = tool_call.get("args", {}).get("thought", "")
                        
                        # Store progress
                        if server_name not in sequential_thinking_progress:
                            sequential_thinking_progress[server_name] = []
                        
                        sequential_thinking_progress[server_name].append({
                            "thought_num": thought_num,
                            "total_thoughts": total_thoughts,
                            "thought_text": thought_text
                        })
                        
                        # Create and send a new message for the sequential thinking step
                        await cl.Message(
                            content=f"🧠 [{server_name}] Thought {thought_num}/{total_thoughts}: {thought_text}"
                        ).send()
                        
                        # If there's a subsequent tool call that's not sequential thinking,
                        # it's likely the action taken based on this thought
                        if len(result["tool_calls"]) > i + 1 and "sequentialthinking" not in result["tool_calls"][i+1].get("name", "").lower():
                            action_tool = result["tool_calls"][i+1]
                            await cl.Message(
                                content=f"🔧 Action based on thought {thought_num}: Using {action_tool.get('name', 'unknown')}"
                            ).send()
                            
                            # Skip the next tool call since we've already displayed it
                            skip_next = True
                    else:
                        # Regular tool execution
                        await cl.Message(
                            content=f"🔧 [{server_name}] Executing: {tool_name}"
                        ).send()
                    
                    # Show args if present
                    if tool_call.get("args") and "sequentialthinking" not in tool_name.lower():
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
                
                # Show sequential thinking summary if applicable
                for server_name, thoughts in sequential_thinking_progress.items():
                    if len(thoughts) > 1:
                        summary = f"🧠 Sequential Thinking Progress ({server_name}):\n"
                        for t in thoughts:
                            summary += f"- Thought {t['thought_num']}/{t['total_thoughts']}: {t['thought_text'][:50]}...\n"
                        await cl.Message(content=summary).send()
            
            # Send the detailed response
            await cl.Message(content=result.get("response", "")).send()
            
            logger.info(f"Final Result before summary: {result}")
            # Generate and send a summary if there were tool calls
            if result.get("tool_calls"):
                try:
                    summary = await orchestrator.generate_summary(result)
                    if summary:
                        await cl.Message(content=f"📋 **Summary**: {summary}").send()
                except Exception as e:
                    logger.error(f"Error generating summary: {str(e)}", exc_info=True)
            
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


