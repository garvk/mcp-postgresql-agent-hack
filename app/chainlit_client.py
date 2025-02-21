from typing import Dict, Any, List
from chainlit.types import AskFileResponse
from chainlit.message import Message
import chainlit as cl
from app.multi_client import MCPMultiClient
import asyncio
import logging
from app.llm_orchestrator import LLMOrchestrator

logger = logging.getLogger(__name__)

class ChainlitMCPClient(MCPMultiClient):
    def __init__(self):
        super().__init__()
        self.orchestrator = LLMOrchestrator()

    async def execute_tool(self, tool_name: str, args: Dict) -> Any:
        """Execute a tool with the given name and arguments"""
        try:
            # Parse server name from tool name (e.g., "weather_get_forecast")
            server_name, actual_tool_name = tool_name.split('_', 1)
            
            server = self.servers.get(server_name)
            if not server or server.config.status != "connected":
                raise ValueError(f"Server '{server_name}' not available")

            # Execute tool call on appropriate server
            result = await server.session.call_tool(actual_tool_name, args)
            logger.info(f"Tool {tool_name} executed successfully")
            logger.debug(f"Tool response: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}")
            raise

    async def process_query_with_ui(self, query: str) -> Dict[str, Any]:
        """Process query with Chainlit UI integration using the orchestrator"""
        try:
            # Show thinking indicator
            thinking_msg = cl.Message(content="Thinking...")
            await thinking_msg.send()
            
            # Get available tools from all connected servers
            available_tools = []
            for server in self.servers.values():
                if server.session and server.config.status == "connected":
                    available_tools.extend(server.tools)
            
            # Process query through orchestrator
            result = await self.orchestrator.process_query(
                query=query,
                available_tools=available_tools,
                tool_executor=self.execute_tool
            )
            
            # Remove thinking message only after we have the complete response
            await thinking_msg.remove()
            
            # Send final response through Chainlit
            if result["response"]:
                await cl.Message(content=result["response"]).send()
                
            return result
            
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