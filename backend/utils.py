"""
Utility functions — Pydantic request models, input validators, text helpers, and logging.
"""

import re
import logging
from pydantic import BaseModel, field_validator
from typing import Literal

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_research_assistant")


# --- Pydantic request/response models ---

class ResearchRequest(BaseModel):
    """Request body for POST /research."""
    topic: str

    @field_validator("topic")
    @classmethod
    def topic_must_not_be_empty(cls, v: str) -> str:
        """Validate that the topic is not empty or whitespace-only."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Topic cannot be empty.")
        if len(stripped) > 500:
            raise ValueError("Topic must be 500 characters or fewer.")
        return stripped


class ExportRequest(BaseModel):
    """Request body for POST /export."""
    content: str
    filename: str
    format: Literal["txt", "pdf"]

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, v: str) -> str:
        """Validate that export content is not empty."""
        if not v.strip():
            raise ValueError("Content cannot be empty.")
        return v

    @field_validator("filename")
    @classmethod
    def sanitize_filename(cls, v: str) -> str:
        """Strip special characters from the filename to prevent path traversal."""
        sanitized = re.sub(r"[^\w\s-]", "", v.strip())
        sanitized = re.sub(r"\s+", "_", sanitized)
        return sanitized[:100] if sanitized else "research_output"


class ResearchResponse(BaseModel):
    """Response body for POST /research."""
    summary: str
    sources: list[str]
    topic: str
    model_used: str = ""


# --- Text helpers ---

def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to a maximum length with an ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
