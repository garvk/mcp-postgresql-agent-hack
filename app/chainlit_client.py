from typing import Dict, Any, List
from chainlit.types import AskFileResponse
from chainlit.message import Message
import chainlit as cl
from app.multi_client import MCPMultiClient
import asyncio
import logging

logger = logging.getLogger(__name__)

class ChainlitMCPClient(MCPMultiClient):
    async def process_query_with_ui(self, query: str) -> Dict[str, Any]:
        """Process query with Chainlit UI integration"""
        final_text = []
        tool_calls = []
        
        try:
            # Show thinking indicator
            thinking_msg = cl.Message(content="Thinking...")
            await thinking_msg.send()
            
            # Trim conversation history by token count before adding new query
            self._trim_conversation_history()
            
            messages = self.conversation_history + [{"role": "user", "content": query}]
            available_tools = []
            for server in self.servers.values():
                if server.session and server.config.status == "connected":
                    available_tools.extend(server.tools)

            # Initial Claude call
            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=messages,
                tools=available_tools
            )
            
            # Remove thinking message
            await thinking_msg.remove()

            for content in response.content:
                if content.type == 'text':
                    final_text.append(content.text)
                    await cl.Message(content=content.text).send()
                    
                elif content.type == 'tool_use':
                    tool_name = content.name
                    tool_args = content.input
                    
                    # Reference to original tool execution logic
                    """python:app/multi_client.py
                    startLine: 72
                    endLine: 131
                    """
                    
                    try:
                        # Parse server name and validate tool
                        parts = tool_name.split('_', 1)
                        if len(parts) != 2:
                            raise ValueError(f"Invalid tool name format: {tool_name}")
                            
                        server_name, _ = parts
                        server = self.servers.get(server_name)
                        
                        if not server or server.config.status != "connected":
                            raise ValueError(f"Server '{server_name}' not available")

                        actual_tool_name = server.tool_name_map.get(tool_name)
                        if not actual_tool_name:
                            raise ValueError(f"Tool '{tool_name}' not found")

                        # Show tool execution message
                        tool_msg = cl.Message(content=f"🔧 Using tool: {tool_name}")
                        await tool_msg.send()

                        # Execute tool
                        result = await server.session.call_tool(actual_tool_name, tool_args)
                        
                        # Record tool call
                        tool_call = {
                            "server": server_name,
                            "name": tool_name,
                            "args": tool_args,
                            "result": result.content
                        }
                        tool_calls.append(tool_call)

                        # Show tool result
                        await cl.Message(
                            content=f"Tool Result:\n```json\n{result.content}\n```"
                        ).send()

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
                        await cl.Message(content=follow_up_text).send()

                    except Exception as e:
                        error_msg = f"🔴 Error with {tool_name}: {str(e)}"
                        final_text.append(error_msg)
                        await cl.Message(content=error_msg, type="error").send()
                        logger.error(error_msg, exc_info=True)

            # Trim conversation history
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]

            return {
                "response": "\n".join(final_text),
                "tool_calls": tool_calls
            }

        except Exception as e:
            error_msg = f"Error processing query: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise 

    def _trim_conversation_history(self, max_tokens: int = 150000):
        """Trim conversation history based on token count"""
        while self.conversation_history:
            try:
                # Join all messages into a single string for token counting
                messages_text = " ".join(msg["content"] for msg in self.conversation_history)
                
                # Use the messages.create method with max_tokens=0 to count tokens
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=0,
                    messages=[{"role": "user", "content": messages_text}]
                )
                
                # Get token count from response metadata
                token_count = response.usage.input_tokens
                
                if token_count <= max_tokens:
                    break
                    
                # Remove oldest message if we're over the limit
                self.conversation_history.pop(0)
                logger.info(f"Trimmed conversation history. New token count: {token_count}")
                
            except Exception as e:
                logger.warning(f"Error counting tokens: {str(e)}")
                # Fallback: keep last 5 messages if token counting fails
                if len(self.conversation_history) > 5:
                    self.conversation_history = self.conversation_history[-5:]
                break 