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
  notice  {message}        — non-fatal info, e.g. the user's own API key failed
  done    {sources, model, topic}
  error   {message}
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from backend.config import settings
from backend.pages import is_safe_url
from backend.prompts import RESEARCH_SYSTEM_PROMPT, build_user_prompt
from backend.providers import ModelOption, UserLLM, describe_error, server_model_chain
from backend.search import Source, build_sources_markdown, format_context, gather_sources
from backend.utils import logger

# Server-configured models (module-level name so tests can replace it)
get_model_chain = server_model_chain


def sse(event_type: str, **data: Any) -> str:
    """Format one Server-Sent Event."""
    return f"data: {json.dumps({'type': event_type, **data})}\n\n"


async def build_chain(user_llm: UserLLM | None) -> tuple[list[ModelOption], str | None]:
    """
    The visitor's own model (if any) first, then the server models.
    Returns the chain and an optional notice for the user.
    """
    chain: list[ModelOption] = []
    notice: str | None = None
    if user_llm is not None:
        if user_llm.provider == "custom" and not await is_safe_url(user_llm.base_url):
            notice = "Your custom base URL is not a public https address, so it was skipped."
        else:
            chain.append(user_llm.to_option())
    return chain + get_model_chain(), notice


async def run_research_workflow(topic: str, user_llm: UserLLM | None = None) -> AsyncGenerator[str, None]:
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

    chain, notice = await build_chain(user_llm)
    if notice:
        yield sse("notice", message=notice)
    if not chain:
        yield sse("error", message="No AI model is available. Add your own API key in Settings, "
                                   "or set OPENROUTER_API_KEY / GROQ_API_KEY on the server.")
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
            logger.warning(f"{option.provider} model {option.model} failed: {describe_error(e)}")
            if option.user_supplied:
                fallback = "using the server's models instead" if len(chain) > 1 else "no other model is available"
                yield sse("notice", message=f"Your {option.provider} model failed: {describe_error(e)}; {fallback}.")
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
