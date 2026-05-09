"""
Configuration module — single source of truth for all settings.
Reads from .env file using pydantic-settings. Never use os.environ directly.
Supports dual-model safety: OpenRouter (primary) + Groq (fallback).
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Dual-model API keys
    openrouter_api_key: str = ""
    groq_api_key: str = ""

    # Triple-model configuration (Primary → Fallback 1 → Fallback 2)
    primary_model: str = "openai/gpt-oss-120b:free"
    fallback_model: str = "llama-3.3-70b-versatile"
    fallback_model_2: str = "llama-3.1-8b-instant"

    max_tokens: int = 2000
    output_dir: str = "./outputs"

    class Config:
        env_file = ".env"


settings = Settings()
