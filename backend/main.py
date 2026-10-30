"""
FastAPI application entry point — CORS, exception handlers, router, static files.
This file is the entry point ONLY. No business logic here.

Run locally:  uvicorn backend.main:app --reload
"""

import os

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.errors import (
    ExportError,
    export_error_handler,
    generic_error_handler,
    validation_error_handler,
)
from backend.routes import router

FRONTEND_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

app = FastAPI(
    title="AI Research Assistant",
    description="AI research agent with MCP web search, academic paper search and PDF export",
    version="1.1.0",
)

# CORS — configure CORS_ORIGINS in .env to restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(ExportError, export_error_handler)
app.add_exception_handler(Exception, generic_error_handler)

app.include_router(router)

# Serve the frontend from the same server (mounted last so API routes win)
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
