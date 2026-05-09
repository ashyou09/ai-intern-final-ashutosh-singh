"""
Core AI orchestration — Agent with MCP tool-use loop.

Architecture:
  - Primary model: OpenRouter (gpt-oss-120b:free) via OpenAI-compatible API
  - Fallback model: Groq (llama-3.3-70b-versatile) if primary fails
  - Tool execution: MCP web_search server via stdio subprocess
  - Direct fallback: DuckDuckGo if MCP server is unavailable

MCP Integration:
  The agent calls tools via `mcp_client.call_tool_subprocess()`, which
  spawns `backend/mcp_runner.py` as a clean subprocess. That runner
  connects to the MCP server via stdio, executes the tool, and returns
  the result via stdout. This cleanly separates event loops.
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator
import asyncio

from openai import AsyncOpenAI
from groq import AsyncGroq
from duckduckgo_search import DDGS

from backend.mcp_client import call_tool_subprocess
from backend.prompts import RESEARCH_SYSTEM_PROMPT
from backend.config import settings
from backend.errors import ClaudeAPIError
from backend.utils import logger


# Tool definitions removed in favor of explicit chaining workflow


# =========================================================================
# Tool Execution — MCP subprocess first, DuckDuckGo fallback
# =========================================================================

def _execute_web_search(query: str, num_results: int = 5) -> str:
    """
    Execute a web search. Tries MCP server (via subprocess) first,
    then falls back to direct DuckDuckGo call if MCP fails.

    Args:
        query: The search query string.
        num_results: Number of results to return (1-10).

    Returns:
        JSON string with list of {title, url, snippet} objects.
    """
    # --- MCP Server (proper subprocess integration) ---
    try:
        result: str = call_tool_subprocess(
            server_script="mcp_servers/web_search_server.py",
            tool_name="web_search",
            tool_input={"query": query, "num_results": num_results},
        )
        if result and "error" not in result.lower()[:50]:
            logger.info("[MCP] web_search succeeded via MCP subprocess")
            return result
    except Exception as e:
        logger.warning(f"[MCP] web_search failed, falling back to direct: {e}")

    # --- Fallback: Direct DuckDuckGo ---
    try:
        with DDGS() as ddgs:
            raw_results: list[dict[str, str]] = list(
                ddgs.text(query, max_results=min(num_results, 10))
            )
        results: list[dict[str, str]] = [
            {
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
            }
            for item in raw_results
        ]
        return json.dumps(results)
    except Exception as e:
        logger.error(f"DuckDuckGo fallback also failed: {e}")
        return json.dumps([{"error": f"All search methods failed: {str(e)}"}])


def _search_academic_papers(query: str, num_results: int = 5) -> str:
    """
    Search for academic papers using DuckDuckGo with scholar-targeted queries.

    Targets arXiv, PubMed, Semantic Scholar, and Google Scholar.

    Args:
        query: The academic research query.
        num_results: Number of papers to return (1-10).

    Returns:
        JSON string with list of {title, url, abstract, source} objects.
    """
    try:
        # A simpler query that DuckDuckGo handles much better
        academic_query: str = f"{query} research paper pdf arxiv OR google scholar"
        with DDGS() as ddgs:
            raw_results: list[dict[str, str]] = list(
                ddgs.text(academic_query, max_results=min(num_results, 10))
            )
        papers: list[dict[str, str]] = [
            {
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "abstract": item.get("body", ""),
                "source": _detect_source(item.get("href", "")),
            }
            for item in raw_results
        ]
        return json.dumps(papers)
    except Exception as e:
        logger.error(f"Academic search failed: {e}")
        return json.dumps([{"error": f"Academic search failed: {str(e)}"}])


def _detect_source(url: str) -> str:
    """Detect the academic source from a URL."""
    source_map: dict[str, str] = {
        "arxiv.org": "arXiv",
        "scholar.google": "Google Scholar",
        "semanticscholar": "Semantic Scholar",
        "pubmed": "PubMed",
        "ieee": "IEEE",
        "acm.org": "ACM",
    }
    for pattern, name in source_map.items():
        if pattern in url:
            return name
    return "Web"




# =========================================================================
# Main Streaming Workflow
# =========================================================================

async def run_research_workflow(topic: str) -> AsyncGenerator[str, None]:
    """
    Run the research workflow. Gathers data first, then streams the response.
    """
    sources: list[str] = []

    yield f"data: {json.dumps({'type': 'status', 'message': f'Starting research on: {topic}'})}\n\n"
    await asyncio.sleep(0.1)

    yield f"data: {json.dumps({'type': 'status', 'message': 'Searching the web and academic databases...'})}\n\n"
    
    # Run the web search and academic search concurrently in thread pool
    web_results, academic_results = await asyncio.gather(
        asyncio.to_thread(_execute_web_search, topic, 5),
        asyncio.to_thread(_search_academic_papers, topic, 3)
    )
    _extract_sources(web_results, sources)
    _extract_sources(academic_results, sources)

    yield f"data: {json.dumps({'type': 'status', 'message': 'Analyzing gathered information...'})}\n\n"

    # Formulate the prompt with the gathered data
    context = f"Web Search Results:\n{web_results}\n\nAcademic Papers:\n{academic_results}"
    
    base_messages = [
        {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": f"Research the following topic thoroughly: {topic}\n\nHere is the gathered context to base your research on:\n{context}"},
    ]

    # Models chain list
    models_to_try = []
    if settings.openrouter_api_key and not settings.openrouter_api_key.startswith("your-"):
        models_to_try.append({
            "provider": "OpenRouter",
            "model": settings.primary_model,
            "client": AsyncOpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)
        })
    if settings.groq_api_key and not settings.groq_api_key.startswith("your-"):
        models_to_try.append({
            "provider": "Groq-70B",
            "model": settings.fallback_model,
            "client": AsyncGroq(api_key=settings.groq_api_key)
        })
        models_to_try.append({
            "provider": "Groq-8B",
            "model": settings.fallback_model_2,
            "client": AsyncGroq(api_key=settings.groq_api_key)
        })

    for config in models_to_try:
        try:
            logger.info(f"Trying {config['provider']} model: {config['model']}")
            yield f"data: {json.dumps({'type': 'status', 'message': f'Generating summary using {config['provider']}...'})}\n\n"
            stream = await config['client'].chat.completions.create(
                model=config['model'],
                messages=base_messages,
                max_tokens=settings.max_tokens,
                stream=True
            )
            
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text_chunk = chunk.choices[0].delta.content
                    yield f"data: {json.dumps({'type': 'content', 'text': text_chunk})}\n\n"
            
            # End of stream
            logger.info(f"{config['provider']} model succeeded")
            yield f"data: {json.dumps({'type': 'done', 'sources': list(set(sources)), 'model': config['model'], 'topic': topic})}\n\n"
            return
            
        except Exception as e:
            logger.warning(f"{config['provider']} model failed: {e}")

    # If all fail
    error_msg = "All AI models failed. Please check your API keys."
    logger.error(error_msg)
    yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
    raise ClaudeAPIError(error_msg)


def _extract_sources(result: str, sources: list[str]) -> None:
    """Extract URLs from tool results and add them to the sources list."""
    try:
        data: Any = json.loads(result)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "url" in item:
                    url: str = item["url"]
                    if url and not url.startswith("https://example.com"):
                        sources.append(url)
    except (json.JSONDecodeError, TypeError):
        pass
