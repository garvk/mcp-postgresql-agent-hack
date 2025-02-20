from contextlib import AsyncExitStack
from typing import Dict, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.config import ServerConfig
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class ServerConnection:
    def __init__(self, name: str, config: ServerConfig):
        self.name = name
        self.config = config
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.tools: List[Dict] = []

    
    async def initialize(self) -> List[Dict]:
        """Initialize server connection and return available tools"""
        try:
            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=None
            )
            
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            self.stdio, self.write = stdio_transport
            self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
            
            await self.session.initialize()
            response = await self.session.list_tools()
            
            # Store original tool names for lookup
            self.tool_name_map = {}
            self.tools = []
            
            for tool in response.tools:
                # Create Claude-compatible tool name
                claude_name = f"{self.name}_{tool.name}".replace('.', '_')
                self.tool_name_map[claude_name] = tool.name
                
                self.tools.append({
                    "type": "custom",  # Changed from "function" to "custom"
                    "name": claude_name,
                    "description": f"[{self.name}] {tool.description}",
                    "parameters": {
                        "type": "object",
                        "properties": tool.inputSchema.get("properties", {}),
                        "required": tool.inputSchema.get("required", [])
                    }
                })
            
            self.config.status = "connected"
            logger.info(f"Successfully initialized server {self.name} with {len(self.tools)} tools")
            return self.tools
                    
        except Exception as e:
            self.config.status = "failed"
            # Ensure cleanup on initialization failure
            try:
                await self.exit_stack.aclose()
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup after failed initialization: {cleanup_error}")
            raise ConnectionError(f"Failed to initialize server {self.name}: {str(e)}")


# class ServerConnection:
#     def __init__(self, name: str, config: ServerConfig):
#         self.name = name
#         self.config = config
#         self.session: Optional[ClientSession] = None
#         self.exit_stack = AsyncExitStack()
#         self.tools: List[Dict] = []
        
#     async def initialize(self) -> List[Dict]:
#         """Initialize server connection and return available tools"""
#         try:
#             server_params = StdioServerParameters(
#                 command=self.config.command,
#                 args=self.config.args,
#                 env=None
#             )
            
#             stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
#             self.stdio, self.write = stdio_transport
#             self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
            
#             await self.session.initialize()
#             response = await self.session.list_tools()
            
#             self.tools = [{
#                 "name": f"{self.name}.{tool.name}",
#                 "description": tool.description,
#                 "input_schema": tool.inputSchema
#             } for tool in response.tools]
            
#             self.config.status = "connected"
#             return self.tools
            
#         except Exception as e:
#             self.config.status = "failed"
#             raise ConnectionError(f"Failed to connect to {self.name}: {str(e)}")