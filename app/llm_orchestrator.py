from typing import Dict, List, Optional, Any
from anthropic import Anthropic
import logging
import json
from pydantic import BaseModel

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConversationMemory(BaseModel):
    messages: List[Dict[str, str]] = []
    max_messages: int = 10
    
    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]

class ToolResponse(BaseModel):
    """Model for standardizing tool responses"""
    content: str
    metadata: Optional[Dict] = None
    status: str = "success"
    
    @classmethod
    def from_mcp_response(cls, response: Any) -> "ToolResponse":
        """Create ToolResponse from MCP response"""
        try:
            # Handle MCP TextContent/CallToolResult
            if hasattr(response, 'content'):
                # If content is a list (CallToolResult), join text content
                if isinstance(response.content, list):
                    content_texts = []
                    for item in response.content:
                        if hasattr(item, 'text'):
                            content_texts.append(item.text)
                        elif isinstance(item, str):
                            content_texts.append(item)
                    content = "\n".join(content_texts)
                else:
                    content = response.content

                return cls(
                    content=content,
                    status="error" if getattr(response, 'isError', False) else "success",
                    metadata={"raw_type": type(response).__name__}
                )
            
            # Handle string response
            if isinstance(response, str):
                return cls(content=response)
            
            # Handle dict response
            if isinstance(response, dict):
                return cls(
                    content=str(response.get("content", "")),
                    metadata=response.get("metadata", {}),
                    status=response.get("status", "success")
                )
            
            # Fallback
            return cls(
                content=str(response),
                metadata={"raw_type": type(response).__name__}
            )
            
        except Exception as e:
            logger.error(f"Error parsing tool response: {e}")
            return cls(
                content=str(response),
                status="error",
                metadata={"error": str(e)}
            )

class LLMOrchestrator:
    def __init__(self):
        self.anthropic = Anthropic()
        self.memory = ConversationMemory()
        
    def _build_system_prompt(self, tools: List[Dict]) -> str:
        tool_descriptions = "\n".join([
            f"- {tool['name']}: {tool['description']}"
            for tool in tools
        ])
        
        return f"""You are a helpful AI assistant with access to these tools:

{tool_descriptions}

When using tools:
1. Choose the most appropriate tool based on the user's request
2. You can use multiple tools if needed
3. Format tool results into natural, conversational responses
4. Keep responses concise but informative
5. Focus on the most relevant information

If no tool is needed, respond directly to the user's query.
"""

    async def _execute_tool(self, 
                          tool_name: str, 
                          tool_args: Dict,
                          tool_executor: callable) -> ToolResponse:
        """Execute tool and process response"""
        try:
            logger.info(f"Executing tool: {tool_name}")
            logger.info(f"Tool arguments: {tool_args}")
            
            raw_result = await tool_executor(tool_name, tool_args)
            logger.debug(f"Raw result type: {type(raw_result)}")
            
            tool_response = ToolResponse.from_mcp_response(raw_result)
            logger.info(f"Processed tool response: {tool_response.model_dump()}")
            
            return tool_response
            
        except Exception as e:
            logger.error(f"Tool execution error: {str(e)}", exc_info=True)
            return ToolResponse(
                content=f"Error executing {tool_name}: {str(e)}",
                status="error",
                metadata={"error": str(e)}
            )

    async def process_query(self, 
                          query: str,
                          available_tools: List[Dict],
                          tool_executor: callable) -> Dict[str, Any]:
        """Process a user query using available tools and conversation memory."""
        try:
            self.memory.add_message("user", query)
            final_text = []
            tool_calls = []
            
            while True:  # Continue until we get a complete response
                logger.info("Making Anthropic API call...")
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    system=self._build_system_prompt(available_tools),
                    messages=self.memory.messages,
                    tools=available_tools
                )
                
                # Log the complete response
                logger.info("Received Anthropic API response:")
                logger.info(f"Response ID: {response.id}")
                logger.info(f"Model: {response.model}")
                logger.info(f"Role: {response.role}")
                logger.info("Content items:")
                for idx, content in enumerate(response.content):
                    logger.info(f"  Item {idx + 1}:")
                    logger.info(f"    Type: {content.type}")
                    if content.type == 'text':
                        logger.info(f"    Text: {content.text}")
                    elif content.type == 'tool_use':
                        logger.info(f"    Tool: {content.name}")
                        logger.info(f"    Arguments: {content.input}")
                
                for content in response.content:
                    if content.type == 'text':
                        final_text.append(content.text)
                        self.memory.add_message("assistant", content.text)
                        
                    elif content.type == 'tool_use':
                        tool_response = await self._execute_tool(
                            content.name,
                            content.input,
                            tool_executor
                        )
                        
                        tool_calls.append({
                            "name": content.name,
                            "args": content.input,
                            "response": tool_response.model_dump()
                        })
                        
                        # Add tool interaction to memory
                        self.memory.add_message(
                            "assistant",
                            f"Using tool {content.name}..."
                        )
                        
                        # Add tool result to memory
                        if isinstance(tool_response.content, dict):
                            # Handle structured responses (like from sequential thinking)
                            next_thought_needed = tool_response.content.get("nextThoughtNeeded", False)
                            result_text = tool_response.content.get("result", str(tool_response.content))
                            self.memory.add_message("user", f"Tool result: {result_text}")
                            
                            if content.name == "sequential-thinking_sequentialthinking" and not next_thought_needed:
                                return {
                                    "response": "\n".join(final_text),
                                    "tool_calls": tool_calls
                                }
                        else:
                            # Handle simple string responses
                            self.memory.add_message("user", f"Tool result: {tool_response.content}")
                
                # If we didn't get a tool call, we're done
                if not any(c.type == 'tool_use' for c in response.content):
                    logger.info("No more tool calls needed, completing response")
                    break
                
            return {
                "response": "\n".join(final_text),
                "tool_calls": tool_calls
            }
            
        except Exception as e:
            logger.error(f"Orchestration error: {str(e)}", exc_info=True)
            raise
