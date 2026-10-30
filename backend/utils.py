"""
Utility module — logging setup and Pydantic request models with validators.
"""

import logging
import re
from typing import Literal

from pydantic import BaseModel, field_validator

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai_research_assistant")

MAX_TOPIC_LENGTH: int = 500
MAX_EXPORT_CHARS: int = 200_000


# --- Pydantic request models ---

class ResearchRequest(BaseModel):
    """Request body for POST /research."""
    topic: str

    @field_validator("topic")
    @classmethod
    def topic_must_be_valid(cls, v: str) -> str:
        """Validate that the topic is non-empty and within the length limit."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Topic cannot be empty.")
        if len(stripped) > MAX_TOPIC_LENGTH:
            raise ValueError(f"Topic must be {MAX_TOPIC_LENGTH} characters or fewer.")
        return stripped


class ExportRequest(BaseModel):
    """Request body for POST /export."""
    content: str
    filename: str
    format: Literal["txt", "pdf"]

    @field_validator("content")
    @classmethod
    def content_must_be_valid(cls, v: str) -> str:
        """Validate that export content is non-empty and not oversized."""
        if not v.strip():
            raise ValueError("Content cannot be empty.")
        if len(v) > MAX_EXPORT_CHARS:
            raise ValueError("Content is too large to export.")
        return v

    @field_validator("filename")
    @classmethod
    def sanitize_filename(cls, v: str) -> str:
        """Strip special characters from the filename (no path traversal, no header injection)."""
        sanitized = re.sub(r"[^\w\s-]", "", v.strip(), flags=re.ASCII)
        sanitized = re.sub(r"\s+", "_", sanitized)
        return sanitized[:100] if sanitized else "research_output"
