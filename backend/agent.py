"""
Core AI orchestration — gathers sources, then streams a cited summary.

Workflow:
  1. search.gather_sources() runs web search (MCP server, DuckDuckGo fallback)
     and academic search (arXiv + Semantic Scholar) concurrently.
  2. Sources are numbered and passed to the model as plain text.
  3. The model chain (OpenRouter → Groq 70B → Groq 8B) streams the summary.
     If a model fails mid-stream, a `reset` event tells the client to discard
     the partial text before the next model starts.
  4. A numbered "Sources" section is appended programmatically, so the
     citations always point at real URLs.

SSE events (all JSON in `data:` lines):
  status  {stage: search|analyze|write, message}
  content {text}
  reset   {message}        — discard streamed text, a fallback model is starting
  done    {sources, model, topic}
  error   {message}
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, AsyncGenerator

from groq import AsyncGroq
from openai import AsyncOpenAI

from backend.config import settings
from backend.prompts import RESEARCH_SYSTEM_PROMPT, build_user_prompt
from backend.search import Source, build_sources_markdown, format_context, gather_sources
from backend.utils import logger

OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"


@dataclass(frozen=True)
class ModelOption:
    provider: str
    model: str
    client: Any


def _key_is_set(key: str) -> bool:
    return bool(key) and not key.startswith("your-")


@lru_cache(maxsize=1)
def _openrouter_client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=OPENROUTER_BASE_URL, api_key=settings.openrouter_api_key)


@lru_cache(maxsize=1)
def _groq_client() -> AsyncGroq:
    return AsyncGroq(api_key=settings.groq_api_key)


def get_model_chain() -> list[ModelOption]:
    """Return the configured models in fallback order. Clients are reused across requests."""
    chain: list[ModelOption] = []
    if _key_is_set(settings.openrouter_api_key):
        chain.append(ModelOption("OpenRouter", settings.primary_model, _openrouter_client()))
    if _key_is_set(settings.groq_api_key):
        chain.append(ModelOption("Groq", settings.fallback_model, _groq_client()))
        chain.append(ModelOption("Groq", settings.fallback_model_2, _groq_client()))
    return chain


def sse(event_type: str, **data: Any) -> str:
    """Format one Server-Sent Event."""
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


async def run_research_workflow(topic: str) -> AsyncGenerator[str, None]:
    """Gather sources, then stream the model's summary as SSE events."""
    yield sse("status", stage="search", message="Searching the web and academic databases...")

    try:
        sources: list[Source] = await gather_sources(topic)
    except Exception as e:
        logger.error(f"Source gathering failed: {e}")
        sources = []
    logger.info(f"Gathered {len(sources)} sources for: {topic}")

    yield sse("status", stage="analyze", message=f"Analyzing {len(sources)} sources...")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(topic, format_context(sources))},
    ]

    chain: list[ModelOption] = get_model_chain()
    if not chain:
        yield sse("error", message="No AI model is configured. Set OPENROUTER_API_KEY or GROQ_API_KEY.")
        return

    for option in chain:
        streamed_any: bool = False
        try:
            logger.info(f"Trying {option.provider} model: {option.model}")
            yield sse("status", stage="write", message=f"Writing summary with {option.model}...")
            stream = await option.client.chat.completions.create(
                model=option.model,
                messages=messages,
                max_tokens=settings.max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    streamed_any = True
                    yield sse("content", text=chunk.choices[0].delta.content)

            if not streamed_any:
                raise RuntimeError("model returned an empty response")

        except Exception as e:
            logger.warning(f"{option.provider} model {option.model} failed: {e}")
            if streamed_any:
                yield sse("reset", message="The model stopped mid-answer; retrying with a fallback model.")
            continue

        references: str = build_sources_markdown(sources)
        if references:
            yield sse("content", text=references)

        logger.info(f"{option.model} succeeded")
        yield sse("done", sources=[s.to_dict() for s in sources], model=option.model, topic=topic)
        return

    logger.error("All AI models failed")
    yield sse("error", message="All AI models failed. Please check your API keys or try again later.")
