"""
Core AI orchestration — gathers sources, then streams a cited summary.

Workflow:
  1. plan_queries() asks the model to split the topic into 2-3 focused
     sub-queries (best-effort; the plain topic is always searched too).
  2. search.gather_sources() searches the web for every query (MCP server,
     DuckDuckGo fallback) and academic papers (arXiv + Semantic Scholar),
     all concurrently, then reads the top pages in full.
  3. Sources are numbered and passed to the model as plain text.
  4. The model chain (your own key if set → OpenRouter → Groq) streams the summary.
     If a model fails mid-stream, a `reset` event tells the client to discard
     the partial text before the next model starts.
  5. A numbered "Sources" section is appended programmatically, so the
     citations always point at real URLs.

SSE events (all JSON in `data:` lines):
  status  {stage: plan|search|analyze|write, message}
  plan    {queries}        — the sub-queries that will be searched
  content {text}
  reset   {message}        — discard streamed text, a fallback model is starting
  notice  {message}        — non-fatal info, e.g. the user's own API key failed
  done    {sources, model, topic}
  error   {message}
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from typing import Any

from backend.cache import TTLCache, topic_key
from backend.config import settings
from backend.pages import is_safe_url
from backend.prompts import PLANNER_PROMPT, RESEARCH_SYSTEM_PROMPT, build_user_prompt
from backend.providers import ModelOption, UserLLM, describe_error, server_model_chain
from backend.search import Source, build_sources_markdown, format_context, gather_sources
from backend.utils import logger

# Server-configured models (module-level name so tests can replace it)
get_model_chain = server_model_chain

# topic → (planned queries, sources); repeated topics skip planning and searching
source_cache = TTLCache(ttl=settings.cache_ttl, max_entries=200)


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


def parse_queries(text: str, limit: int) -> list[str]:
    """Pull a list of search queries out of the planner's reply (tolerates extra prose)."""
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    queries: list[str] = []
    for item in items:
        if isinstance(item, str):
            q = " ".join(item.split())[:150]
            if q and q.lower() not in (x.lower() for x in queries):
                queries.append(q)
    return queries[:limit]


async def plan_queries(topic: str, chain: list[ModelOption]) -> list[str]:
    """
    Ask the first model that answers to split the topic into focused sub-queries.
    Planning is best-effort: on any failure the plain topic is searched.
    """
    if not settings.plan_queries:
        return []
    prompt = PLANNER_PROMPT.format(n=settings.max_subqueries)
    for option in chain:
        try:
            resp = await asyncio.wait_for(
                option.client.chat.completions.create(
                    model=option.model,
                    messages=[{"role": "system", "content": prompt}, {"role": "user", "content": topic}],
                    max_tokens=200,
                    temperature=0.2,
                ),
                timeout=20,
            )
            queries = parse_queries(resp.choices[0].message.content or "", settings.max_subqueries)
            if queries:
                logger.info(f"Planned queries: {queries}")
                return queries
        except Exception as e:
            logger.info(f"Query planning with {option.model} failed: {describe_error(e)}")
    return []


async def run_research_workflow(topic: str, user_llm: UserLLM | None = None) -> AsyncGenerator[str, None]:
    """Plan searches, gather sources, then stream the model's summary as SSE events."""
    chain, notice = await build_chain(user_llm)
    if notice:
        yield sse("notice", message=notice)
    if not chain:
        yield sse("error", message="No AI model is available. Add your own API key in Settings, "
                                   "or set OPENROUTER_API_KEY / GROQ_API_KEY on the server.")
        return

    queries: list[str]
    sources: list[Source]
    cached = source_cache.get(topic_key(topic))
    if cached:
        queries, sources = cached
        logger.info(f"Using cached sources for: {topic}")
        if queries:
            yield sse("plan", queries=queries)
        yield sse("status", stage="search", message="Using recently gathered sources...", cached=True)
    else:
        yield sse("status", stage="plan", message="Planning searches...")
        queries = await plan_queries(topic, chain)
        if queries:
            yield sse("plan", queries=queries)

        yield sse("status", stage="search", message="Searching the web and academic databases...")
        try:
            sources = await gather_sources(topic, queries)
        except Exception as e:
            logger.error(f"Source gathering failed: {e}")
            sources = []
        if sources:
            source_cache.set(topic_key(topic), (queries, sources))
        logger.info(f"Gathered {len(sources)} sources for: {topic}")

    read: int = sum(1 for s in sources if s.content)
    yield sse("status", stage="analyze",
              message=f"Analyzing {len(sources)} sources" + (f" ({read} pages read in full)..." if read else "..."))

    messages: list[dict[str, str]] = [
        {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(topic, format_context(sources))},
    ]

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
