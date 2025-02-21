from pydantic import BaseModel, Field
from typing import Dict, List
import json
import os

class ServerConfig(BaseModel):
    command: str
    args: List[str]
    status: str = Field(default="initializing")

class MCPConfig(BaseModel):
    mcpServers: Dict[str, ServerConfig]

    @classmethod
    def from_env(cls) -> "MCPConfig":
        config_path = os.getenv("MCP_CONFIG_PATH", "./mcp_config.json")
        with open(config_path) as f:
            return cls.model_validate(json.load(f))