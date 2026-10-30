"""
AI providers — every supported provider speaks the OpenAI-compatible
chat completions API, so one client type (AsyncOpenAI) covers all of them.

Two sources of models:
  1. Server models, configured in .env (OpenRouter → Groq 70B → Groq 8B).
  2. "Bring your own key": a visitor can pick a provider in the web UI and
     paste their own API key. Their model is tried first and the server
     models remain the fallback. The key is used for that request only —
     it is never stored, logged or returned by the server.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, SecretStr, field_validator, model_validator

from backend.config import settings


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    name: str
    base_url: str
    default_model: str
    key_url: str


PROVIDERS: dict[str, ProviderPreset] = {p.id: p for p in [
    ProviderPreset("openrouter", "OpenRouter", "https://openrouter.ai/api/v1",
                   "openai/gpt-oss-120b:free", "https://openrouter.ai/keys"),
    ProviderPreset("groq", "Groq", "https://api.groq.com/openai/v1",
                   "llama-3.3-70b-versatile", "https://console.groq.com/keys"),
    ProviderPreset("openai", "OpenAI", "https://api.openai.com/v1",
                   "gpt-4o-mini", "https://platform.openai.com/api-keys"),
    ProviderPreset("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/",
                   "gemini-2.0-flash", "https://aistudio.google.com/apikey"),
    ProviderPreset("deepseek", "DeepSeek", "https://api.deepseek.com/v1",
                   "deepseek-chat", "https://platform.deepseek.com/api_keys"),
    ProviderPreset("mistral", "Mistral", "https://api.mistral.ai/v1",
                   "mistral-small-latest", "https://console.mistral.ai/api-keys"),
    ProviderPreset("custom", "Custom (OpenAI-compatible)", "", "", ""),
]}

_MODEL_RE = re.compile(r"^[\w.:/@+-]{1,120}$")


@dataclass(frozen=True)
class ModelOption:
    provider: str
    model: str
    client: Any
    user_supplied: bool = False


class UserLLM(BaseModel):
    """A visitor's own provider settings, sent with a research request."""

    provider: str
    api_key: SecretStr          # SecretStr keeps the key out of logs and reprs
    model: str = ""
    base_url: str = ""          # only used by the "custom" provider

    @field_validator("provider")
    @classmethod
    def known_provider(cls, v: str) -> str:
        if v not in PROVIDERS:
            raise ValueError(f"Unknown provider '{v}'.")
        return v

    @field_validator("api_key")
    @classmethod
    def plausible_key(cls, v: SecretStr) -> SecretStr:
        key = v.get_secret_value().strip()
        if not 8 <= len(key) <= 400 or any(c.isspace() for c in key):
            raise ValueError("The API key does not look valid.")
        return SecretStr(key)

    @field_validator("model")
    @classmethod
    def valid_model(cls, v: str) -> str:
        v = v.strip()
        if v and not _MODEL_RE.match(v):
            raise ValueError("Model name contains invalid characters.")
        return v

    @model_validator(mode="after")
    def custom_needs_base_url(self) -> UserLLM:
        if self.provider == "custom":
            if not self.base_url.startswith("https://"):
                raise ValueError("A custom provider needs an https:// base URL.")
            if not self.model:
                raise ValueError("A custom provider needs a model name.")
        else:
            self.base_url = ""
        return self

    @property
    def preset(self) -> ProviderPreset:
        return PROVIDERS[self.provider]

    def to_option(self) -> ModelOption:
        """Build a model option with a per-request client (never cached)."""
        client = AsyncOpenAI(
            base_url=self.base_url or self.preset.base_url,
            api_key=self.api_key.get_secret_value(),
            max_retries=0,
        )
        return ModelOption(self.preset.name, self.model or self.preset.default_model, client, user_supplied=True)


def _key_is_set(key: str) -> bool:
    return bool(key) and not key.startswith("your-")


@lru_cache(maxsize=4)
def _server_client(provider_id: str, api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=PROVIDERS[provider_id].base_url, api_key=api_key)


def server_model_chain() -> list[ModelOption]:
    """The models configured in .env, in fallback order. Clients are reused across requests."""
    chain: list[ModelOption] = []
    if _key_is_set(settings.openrouter_api_key):
        client = _server_client("openrouter", settings.openrouter_api_key)
        chain.append(ModelOption("OpenRouter", settings.primary_model, client))
    if _key_is_set(settings.groq_api_key):
        client = _server_client("groq", settings.groq_api_key)
        chain.append(ModelOption("Groq", settings.fallback_model, client))
        chain.append(ModelOption("Groq", settings.fallback_model_2, client))
    return chain


def describe_error(exc: Exception) -> str:
    """
    A short, key-free description of a provider error for the user.
    Provider messages can echo part of the API key, so they are never forwarded.
    """
    status = getattr(exc, "status_code", None)
    return {
        401: "the API key was rejected (401)",
        402: "the account has no credit left (402)",
        403: "access was denied (403)",
        404: "the model was not found (404)",
        429: "the rate limit or quota was reached (429)",
    }.get(status, f"the provider returned an error ({status})" if status else "the request failed")
