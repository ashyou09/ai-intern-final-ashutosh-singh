"""
Configuration module — single source of truth for all settings.
Reads from .env file using pydantic-settings. Never use os.environ directly.
Model chain: OpenRouter (primary) → Groq 70B → Groq 8B.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # API keys
    openrouter_api_key: str = ""
    groq_api_key: str = ""

    # Model chain (Primary → Fallback 1 → Fallback 2)
    primary_model: str = "openai/gpt-oss-120b:free"
    fallback_model: str = "llama-3.3-70b-versatile"
    fallback_model_2: str = "llama-3.1-8b-instant"
    max_tokens: int = 2000

    # Search
    web_results: int = 6
    paper_results: int = 4
    snippet_chars: int = 400
    http_timeout: float = 15.0
    mcp_timeout: int = 30

    # Comma-separated list of allowed origins, e.g. "https://myapp.vercel.app"
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
