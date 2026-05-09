#!/usr/bin/env python3
"""
MCP Tool Runner — Standalone script for executing MCP tool calls via stdio.

This script is invoked as a subprocess to avoid async event-loop conflicts
between FastAPI (uvicorn) and MCP's anyio-based stdio_client.

Usage:
    python backend/mcp_runner.py <server_script> <tool_name> '<json_args>'

Example:
    python backend/mcp_runner.py mcp_servers/web_search_server.py web_search '{"query": "AI"}'

The result is printed to stdout as a string, which the parent process captures.
"""

import sys
import json
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run_tool(server_script: str, tool_name: str, tool_args: dict[str, object]) -> str:
    """
    Connect to an MCP server via stdio, call a tool, and return the text result.

    Args:
        server_script: Path to the MCP server Python script.
        tool_name: Name of the tool to invoke.
        tool_args: Dictionary of arguments to pass to the tool.

    Returns:
        The concatenated text output from the tool call.
    """
    server_params = StdioServerParameters(
        command="python",
        args=[server_script],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # Execute the tool
            result = await session.call_tool(tool_name, tool_args)

            # Extract text content from the MCP result
            output_parts: list[str] = []
            for content in result.content:
                if hasattr(content, "text"):
                    output_parts.append(content.text)
                else:
                    output_parts.append(str(content))

            return "\n".join(output_parts)


def main() -> None:
    """Parse CLI arguments and execute the MCP tool call."""
    if len(sys.argv) != 4:
        print(json.dumps({"error": f"Usage: {sys.argv[0]} <server> <tool> '<args>'"}))
        sys.exit(1)

    server_script: str = sys.argv[1]
    tool_name: str = sys.argv[2]
    tool_args: dict[str, object] = json.loads(sys.argv[3])

    try:
        result: str = asyncio.run(run_tool(server_script, tool_name, tool_args))
        print(result)
    except Exception as e:
        print(json.dumps({"error": f"MCP call failed: {str(e)}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
