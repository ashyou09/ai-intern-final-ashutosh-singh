"""
Custom exception classes and FastAPI error handlers.
Every user-facing error must use one of these — never expose raw stack traces.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class EmptyTopicError(Exception):
    """Raised when the user submits an empty or whitespace-only topic."""
    pass


class TopicTooLongError(Exception):
    """Raised when the topic exceeds the maximum allowed length."""
    pass


class ClaudeAPIError(Exception):
    """Raised when the Anthropic Claude API call fails."""
    pass


class MCPConnectionError(Exception):
    """Raised when an MCP server is unreachable or fails to respond."""
    pass


class ExportError(Exception):
    """Raised when .txt or .pdf export generation fails."""
    pass


# --- FastAPI exception handlers (register in main.py) ---

async def empty_topic_handler(request: Request, exc: EmptyTopicError) -> JSONResponse:
    """Handle empty topic submissions with a 400 response."""
    return JSONResponse(status_code=400, content={"error": "Topic cannot be empty."})


async def topic_too_long_handler(request: Request, exc: TopicTooLongError) -> JSONResponse:
    """Handle topics that exceed the character limit."""
    return JSONResponse(status_code=400, content={"error": "Topic must be 500 characters or fewer."})


async def claude_api_handler(request: Request, exc: ClaudeAPIError) -> JSONResponse:
    """Handle Claude API failures with a 500 response."""
    return JSONResponse(status_code=500, content={"error": "AI service unavailable. Please try again."})


async def mcp_connection_handler(request: Request, exc: MCPConnectionError) -> JSONResponse:
    """Handle MCP server connection failures with a 503 response."""
    return JSONResponse(status_code=503, content={"error": "Research tool unavailable. Check MCP server."})


async def export_error_handler(request: Request, exc: ExportError) -> JSONResponse:
    """Handle export failures with a 500 response."""
    return JSONResponse(status_code=500, content={"error": "Export generation failed. Please try again."})


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler — log internal details, return safe message to users."""
    import logging
    logging.getLogger("ai_research_assistant").error(f"Unhandled error: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "An unexpected error occurred. Please try again."})

