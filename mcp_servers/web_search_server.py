"""
MCP Server: Web Search Tool
Provides a web_search tool to the AI agent via the MCP protocol.
Uses DuckDuckGo Search — completely free, no API key needed.

Run standalone:  python mcp_servers/web_search_server.py
Test with:       mcp dev mcp_servers/web_search_server.py
"""

import json

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from duckduckgo_search import DDGS

mcp = FastMCP("WebSearchMCP", log_level="ERROR")


@mcp.tool(
    name="web_search",
    description="Search the web for current information on a topic. Returns titles, snippets, and URLs.",
)
def web_search(
    query: str = Field(description="The search query to look up"),
    num_results: int = Field(default=5, description="Number of results to return (1-10)"),
) -> str:
    """Search the web using DuckDuckGo and return structured results."""
    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=min(num_results, 10)))

        results = []
        for item in raw_results:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
            })

        return json.dumps(results)

    except Exception as e:
        return json.dumps([{"error": f"Search failed: {str(e)}"}])


if __name__ == "__main__":
    mcp.run()
