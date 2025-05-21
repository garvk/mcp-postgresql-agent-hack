#!/usr/bin/env python3
import asyncio
import logging
import os
import sys
from typing import Dict, Any

from app.config import MCPConfig
from app.orchestration.orchestrator import Orchestrator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main(query: str):
    try:
        # Initialize orchestrator
        orchestrator = Orchestrator()
        
        # Load MCP configuration
        config = MCPConfig.from_env()
        
        print("\nInitializing MCP servers...")
        # Initialize servers and get their status
        status = await orchestrator.initialize_servers(config)
        
        # Display server status
        for server_name, server_status in status.items():
            print(f"{server_name}: {server_status}")
        
        print("\nProcessing query:", query)
        # Process the query with multi-step reasoning enabled
        result = await orchestrator.process_query(query, multi_step=True)
        
        # Display the response
        print("\nResponse:")
        print(result["response"])
        
        # Display tool usage summary if any tools were used
        if result.get("tool_calls"):
            print("\nTool Usage Summary:")
            for tool_call in result["tool_calls"]:
                status = "✓" if tool_call["status"] == "success" else "✗"
                print(f"{status} {tool_call['name']} ({tool_call['server']})")
        
        # Exit successfully
        os._exit(0)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        print(f"\nError: {str(e)}")
        os._exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python query_mcp.py \"your query here\"")
        os._exit(1)
        
    query = sys.argv[1]
    try:
        asyncio.run(main(query))
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        os._exit(1)
