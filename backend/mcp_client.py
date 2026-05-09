"""
MCP client bridge — connects to MCP servers via stdio subprocess.

Provides two modes:
  1. Subprocess mode (call_tool_subprocess): Runs a dedicated mcp_runner.py script
     in a clean subprocess. This avoids async event-loop conflicts between FastAPI
     and MCP's anyio-based stdio_client. Used by the agent in production.
  2. Async context manager mode (MCPClient): Direct async connection for standalone
     scripts and testing.

See CLAUDE_MCP_AND_CLAUDECODE_GUIDE.md → Section 1.9 for the MCP pattern.
"""

from __future__ import annotations

import json
import subprocess
import sys
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl

from backend.utils import logger

# Path to the standalone MCP runner script
_MCP_RUNNER_PATH: str = os.path.join(os.path.dirname(__file__), "mcp_runner.py")


def call_tool_subprocess(
    server_script: str,
    tool_name: str,
    tool_input: dict[str, Any],
    timeout: int = 30,
) -> str:
    """
    Call an MCP tool via a clean subprocess — no async conflicts.

    This spawns backend/mcp_runner.py as a child process, which in turn
    connects to the MCP server via stdio. The result is returned as a string.

    Args:
        server_script: Path to the MCP server script (e.g. 'mcp_servers/web_search_server.py').
        tool_name: Name of the tool to invoke on the MCP server.
        tool_input: Dict of arguments to pass to the tool.
        timeout: Maximum seconds to wait for the subprocess.

    Returns:
        The text output from the MCP tool call.

    Raises:
        RuntimeError: If the subprocess fails or times out.
    """
    logger.info(f"[MCP] Calling {tool_name} on {server_script} via subprocess")

    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, _MCP_RUNNER_PATH, server_script, tool_name, json.dumps(tool_input)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            error_msg: str = result.stderr.strip() or result.stdout.strip() or "Unknown MCP error"
            logger.warning(f"[MCP] Subprocess failed: {error_msg}")
            raise RuntimeError(f"MCP subprocess failed: {error_msg}")

        output: str = result.stdout.strip()
        logger.info(f"[MCP] Tool {tool_name} returned {len(output)} chars")
        return output

    except subprocess.TimeoutExpired:
        logger.warning(f"[MCP] Tool {tool_name} timed out after {timeout}s")
        raise RuntimeError(f"MCP tool {tool_name} timed out after {timeout}s")


class MCPClient:
    """
    Async context manager for direct MCP server connections via stdio.
    Used for standalone testing and scripts that have their own event loop.

    Usage:
        async with MCPClient('mcp_servers/web_search_server.py') as mcp:
            tools = await mcp.list_tools()
            result = await mcp.call_tool('web_search', {'query': 'AI'})
    """

    def __init__(self, server_script: str) -> None:
        """Initialize with the path to the MCP server script."""
        self.server_script: str = server_script
        self._session: ClientSession | None = None
        self._stdio_context: Any = None

    async def __aenter__(self) -> MCPClient:
        """Start the MCP server subprocess and initialize the session."""
        server_params: StdioServerParameters = StdioServerParameters(
            command="python",
            args=[self.server_script],
        )

        # Create the stdio transport
        self._stdio_context = stdio_client(server_params)
        streams: tuple[Any, Any] = await self._stdio_context.__aenter__()
        read_stream, write_stream = streams

        # Create and initialize the client session
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()

        logger.info(f"MCP client connected to: {self.server_script}")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Cleanly shut down the MCP session and subprocess."""
        try:
            if self._session:
                await self._session.__aexit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            logger.warning(f"Session cleanup warning: {e}")

        try:
            if self._stdio_context:
                await self._stdio_context.__aexit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            logger.warning(f"Stdio cleanup warning: {e}")

        logger.info(f"MCP client disconnected from: {self.server_script}")

    async def list_tools(self) -> list[dict[str, Any]]:
        """
        Discover all tools available from the MCP server.
        Returns tools in a format suitable for OpenAI/Groq function-calling APIs.
        """
        assert self._session is not None, "MCPClient must be used as an async context manager"
        result = await self._session.list_tools()
        tools: list[dict[str, Any]] = []
        for tool in result.tools:
            tools.append({
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            })
        return tools

    async def call_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool on the MCP server and return the result as a string."""
        assert self._session is not None, "MCPClient must be used as an async context manager"
        logger.info(f"Calling MCP tool: {tool_name} with input: {tool_input}")
        result = await self._session.call_tool(tool_name, tool_input)

        # Extract text content from the MCP result
        output_parts: list[str] = []
        for content in result.content:
            if hasattr(content, "text"):
                output_parts.append(content.text)
            else:
                output_parts.append(str(content))

        return "\n".join(output_parts)

    async def read_resource(self, uri: str) -> str | dict[str, Any]:
        """Read a resource from the MCP server by its URI."""
        assert self._session is not None, "MCPClient must be used as an async context manager"
        result = await self._session.read_resource(AnyUrl(uri))
        resource = result.contents[0]
        if isinstance(resource, types.TextResourceContents):
            if resource.mimeType == "application/json":
                return json.loads(resource.text)
            return resource.text
        return str(resource)
