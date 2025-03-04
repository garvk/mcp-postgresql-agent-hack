from typing import Any, Optional
import httpx
from mcp.server.fastmcp import FastMCP

# Create an MCP server named "brave-search"
mcp = FastMCP("brave-search")

# We'll later set the Brave API key from environment variables
BRAVE_API_BASE = "https://api.search.brave.com/res/v1"
BRAVE_API_KEY = None  # We'll override this at runtime

async def make_brave_request(url: str) -> Optional[dict[str, Any]]:
    """
    Make a request to the Brave API with proper error handling.
    Must have a valid BRAVE_API_KEY set.
    """
    if not BRAVE_API_KEY:
        raise ValueError("BRAVE_API_KEY environment variable is required")

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_API_KEY
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            # In production, you might log this exception
            return None
        

def format_web_results(data: dict[str, Any]) -> str:
    """Format web search results into readable text."""
    if not data.get("web", {}).get("results"):
        return "No results found."

    results = []
    for result in data["web"]["results"]:
        results.append(
            f"""Title: {result.get('title', '')}
Description: {result.get('description', '')}
URL: {result.get('url', '')}"""
        )

    return "\\n\\n".join(results)


@mcp.tool()
async def brave_web_search(query: str, count: int = 10, offset: int = 0) -> str:
    """
    Performs a web search using the Brave Search API.

    Args:
        query: Search query (max 400 chars, 50 words)
        count: Number of results (1-20, default 10)
        offset: Pagination offset (max 9, default 0)
    """
    # Ensure count is within bounds
    count = min(max(1, count), 20)
    offset = min(max(0, offset), 9)

    # Build URL with parameters
    url = f"{BRAVE_API_BASE}/web/search"
    params = {
        "q": query,
        "count": count,
        "offset": offset
    }
    url = f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"

    data = await make_brave_request(url)
    if not data:
        return "Unable to fetch search results."

    return format_web_results(data)


if __name__ == "__main__":
    import os

    # Get API key from environment
    BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
    if not BRAVE_API_KEY:
        print("Error: BRAVE_API_KEY environment variable is required")
        exit(1)

    # Initialise and run the server using stdio transport
    mcp.run(transport='stdio')