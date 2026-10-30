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
    cache_ttl: int = 3600         # seconds to reuse a topic's sources (0 = no caching)
    plan_queries: bool = True     # let the model split the topic into focused sub-queries
    max_subqueries: int = 3
    web_results: int = 6
    paper_results: int = 4
    snippet_chars: int = 400
    pages_to_read: int = 3        # top web results whose full text is fetched (0 = off)
    page_chars: int = 2500        # max characters of text kept per page
    page_timeout: float = 8.0
    http_timeout: float = 15.0
    use_mcp: bool = True          # run web search through the MCP server (false = call DuckDuckGo directly)
    mcp_timeout: int = 20
    mcp_retry_after: int = 300    # after an MCP failure, skip MCP for this many seconds

    # Rate limits for POST /research, per client IP (0 = unlimited)
    rate_limit_per_minute: int = 5
    rate_limit_per_hour: int = 40
    trust_proxy: bool = False     # use X-Forwarded-For for the client IP (set when behind a proxy)
    vercel: str = ""              # set automatically by Vercel; implies trust_proxy

    # Comma-separated list of allowed origins, e.g. "https://myapp.vercel.app"
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
