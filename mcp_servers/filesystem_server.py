"""
MCP Server: Filesystem Tool
Provides save_research tool and research://saved resource for the Claude agent.
Saves and reads research results from the outputs/ directory.

Run standalone:  python mcp_servers/filesystem_server.py
Test with:       mcp dev mcp_servers/filesystem_server.py
"""

import os
import json
from datetime import datetime

from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("FilesystemMCP", log_level="ERROR")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./outputs")


@mcp.tool(
    name="save_research",
    description="Save a research summary to disk for later retrieval.",
)
def save_research(
    topic: str = Field(description="The research topic"),
    content: str = Field(description="The research summary to save"),
) -> str:
    """Save research content as JSON with metadata."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Generate a safe, timestamped filename
    safe_topic = topic.replace(" ", "_").lower()[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_topic}_{timestamp}.json"
    path = os.path.join(OUTPUT_DIR, filename)

    data = {
        "topic": topic,
        "content": content,
        "saved_at": datetime.now().isoformat(),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return json.dumps({"saved": True, "path": path, "filename": filename})


@mcp.resource("research://saved", mime_type="application/json")
def list_saved_research() -> str:
    """List all previously saved research filenames."""
    if not os.path.exists(OUTPUT_DIR):
        return json.dumps([])
    files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json")]
    return json.dumps(files)


if __name__ == "__main__":
    mcp.run()
