"""
Custom exception classes and FastAPI error handlers.
Every user-facing error uses the same shape: {"error": "<message>"}.
Never expose raw stack traces.
"""

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.utils import logger


class ExportError(Exception):
    """Raised when .txt or .pdf export generation fails."""


# --- FastAPI exception handlers (registered in main.py) ---

async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Turn Pydantic validation errors into a single readable message."""
    errors = exc.errors()
    message: str = "Invalid request."
    if errors:
        # Pydantic prefixes custom validator messages with "Value error, "
        message = str(errors[0].get("msg", message)).removeprefix("Value error, ")
    return JSONResponse(status_code=422, content={"error": message})


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """HTTPExceptions (404, 429, ...) use the same {"error": ...} shape as every other error."""
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)}, headers=exc.headers)


async def export_error_handler(request: Request, exc: ExportError) -> JSONResponse:
    """Handle export failures with a 500 response."""
    return JSONResponse(status_code=500, content={"error": "Export generation failed. Please try again."})


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler — log internal details, return a safe message to users."""
    logger.error(f"Unhandled error: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "An unexpected error occurred. Please try again."})
