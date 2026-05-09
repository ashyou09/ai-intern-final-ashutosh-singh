"""
FastAPI application entry point — CORS, exception handlers, router.
This file is the entry point ONLY. No business logic here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routes import router
from backend.config import settings
from backend.errors import (
    EmptyTopicError,
    TopicTooLongError,
    ClaudeAPIError,
    MCPConnectionError,
    ExportError,
    empty_topic_handler,
    topic_too_long_handler,
    claude_api_handler,
    mcp_connection_handler,
    export_error_handler,
    generic_error_handler,
)

app = FastAPI(
    title="AI Research Assistant",
    description="Claude-powered research agent with MCP tool integration",
    version="1.0.0",
)

# CORS — allow frontend to call the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register custom exception handlers
app.add_exception_handler(EmptyTopicError, empty_topic_handler)
app.add_exception_handler(TopicTooLongError, topic_too_long_handler)
app.add_exception_handler(ClaudeAPIError, claude_api_handler)
app.add_exception_handler(MCPConnectionError, mcp_connection_handler)
app.add_exception_handler(ExportError, export_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

# Include API routes
app.include_router(router, prefix="/api")

# Serve frontend static files from the same server
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
