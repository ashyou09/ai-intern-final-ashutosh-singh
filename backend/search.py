"""
Search layer — gathers sources for a research topic.

  - Web results: MCP web_search server (via subprocess), with a direct
    DuckDuckGo fallback if the MCP server is unavailable.
  - Academic papers: arXiv API + Semantic Scholar API, queried concurrently.
    Both are free and need no API key. If both fail, a scholar-targeted
    DuckDuckGo query is used instead.

All results are normalised into `Source` objects, de-duplicated by URL and
numbered, so the AI can cite them as [1], [2], ... and the same numbers are
used in the final "Sources" section.
"""

from __future__ import annotations

import asyncio
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from typing import Literal

import httpx
from ddgs import DDGS

from backend.config import settings
from backend.mcp_client import call_tool_subprocess
from backend.pages import read_top_pages
from backend.utils import logger

ARXIV_API_URL: str = "https://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API_URL: str = "https://api.semanticscholar.org/graph/v1/paper/search"
_ATOM_NS: dict[str, str] = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass
class Source:
    """A single search result the AI can cite."""

    title: str
    url: str
    snippet: str
    kind: Literal["web", "paper"]
    origin: str = "Web"           # e.g. "arXiv", "Semantic Scholar", "Web"
    year: str = ""
    authors: str = ""
    id: int = 0                   # citation number, assigned by number_sources()
    content: str = ""             # full page text, filled by pages.read_top_pages()

    def to_dict(self) -> dict[str, object]:
        """Public representation sent to the browser (page text is left out)."""
        data = asdict(self)
        data.pop("content")
        data["read"] = bool(self.content)
        return data


def _clean(text: str) -> str:
    """Collapse whitespace (arXiv abstracts contain hard line breaks)."""
    return re.sub(r"\s+", " ", text or "").strip()


def _format_authors(names: list[str]) -> str:
    """'A, B, C, D' -> 'A, B, C et al.'"""
    names = [n for n in names if n]
    if len(names) > 3:
        return ", ".join(names[:3]) + " et al."
    return ", ".join(names)


# =========================================================================
# Web search — MCP subprocess first, DuckDuckGo fallback
# =========================================================================

def _ddgs_text(query: str, num_results: int) -> list[dict[str, str]]:
    """Run a DuckDuckGo text search and return the raw result dicts."""
    return list(DDGS().text(query, max_results=min(num_results, 10)))


def web_search(query: str, num_results: int = 6) -> list[Source]:
    """
    Search the web. Tries the MCP server first, then direct DuckDuckGo.

    Blocking — call it via asyncio.to_thread from async code.
    """
    items: list[dict[str, str]] | None = None

    try:
        raw: str = call_tool_subprocess(
            server_script="mcp_servers/web_search_server.py",
            tool_name="web_search",
            tool_input={"query": query, "num_results": num_results},
        )
        data = json.loads(raw)
        if isinstance(data, list) and not any("error" in item for item in data):
            items = data
            logger.info("[MCP] web_search succeeded via MCP subprocess")
        else:
            logger.warning(f"[MCP] web_search returned an error: {raw[:200]}")
    except Exception as e:
        logger.warning(f"[MCP] web_search failed, falling back to direct: {e}")

    if items is None:
        try:
            items = [
                {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
                for r in _ddgs_text(query, num_results)
            ]
        except Exception as e:
            logger.error(f"DuckDuckGo fallback also failed: {e}")
            return []

    return [
        Source(title=_clean(i.get("title", "")), url=i.get("url", ""),
               snippet=_clean(i.get("snippet", "")), kind="web")
        for i in items
        if i.get("url")
    ]


# =========================================================================
# Academic search — arXiv + Semantic Scholar
# =========================================================================

def parse_arxiv_feed(xml_text: str) -> list[Source]:
    """Parse an arXiv Atom feed into Source objects."""
    root = ET.fromstring(xml_text)
    papers: list[Source] = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        title = _clean(entry.findtext("atom:title", "", _ATOM_NS))
        url = entry.findtext("atom:id", "", _ATOM_NS).strip()
        if not title or not url:
            continue
        authors = [_clean(a.findtext("atom:name", "", _ATOM_NS))
                   for a in entry.findall("atom:author", _ATOM_NS)]
        papers.append(Source(
            title=title,
            url=url.replace("http://", "https://", 1),
            snippet=_clean(entry.findtext("atom:summary", "", _ATOM_NS)),
            kind="paper",
            origin="arXiv",
            year=entry.findtext("atom:published", "", _ATOM_NS)[:4],
            authors=_format_authors(authors),
        ))
    return papers


def parse_semantic_scholar(payload: dict) -> list[Source]:
    """Parse a Semantic Scholar /paper/search response into Source objects."""
    papers: list[Source] = []
    for item in payload.get("data") or []:
        title = _clean(item.get("title") or "")
        url = item.get("url") or ""
        if not title or not url:
            continue
        papers.append(Source(
            title=title,
            url=url,
            snippet=_clean(item.get("abstract") or ""),
            kind="paper",
            origin=item.get("venue") or "Semantic Scholar",
            year=str(item.get("year") or ""),
            authors=_format_authors([a.get("name", "") for a in item.get("authors") or []]),
        ))
    return papers


async def _search_arxiv(client: httpx.AsyncClient, query: str, num_results: int) -> list[Source]:
    resp = await client.get(ARXIV_API_URL, params={
        "search_query": f"all:{query}",
        "max_results": num_results,
        "sortBy": "relevance",
    })
    resp.raise_for_status()
    return parse_arxiv_feed(resp.text)


async def _search_semantic_scholar(client: httpx.AsyncClient, query: str, num_results: int) -> list[Source]:
    resp = await client.get(SEMANTIC_SCHOLAR_API_URL, params={
        "query": query,
        "limit": num_results,
        "fields": "title,url,abstract,year,authors,venue",
    })
    resp.raise_for_status()
    return parse_semantic_scholar(resp.json())


def _ddgs_papers(query: str, num_results: int) -> list[Source]:
    """Last-resort paper search via a scholar-targeted DuckDuckGo query."""
    return [
        Source(title=_clean(r.get("title", "")), url=r.get("href", ""),
               snippet=_clean(r.get("body", "")), kind="paper", origin="Web")
        for r in _ddgs_text(f"{query} research paper arxiv", num_results)
        if r.get("href")
    ]


async def academic_search(query: str, num_results: int = 4) -> list[Source]:
    """
    Search arXiv and Semantic Scholar concurrently and interleave the results.
    Falls back to DuckDuckGo if both APIs fail or return nothing.
    """
    per_source: int = max(1, num_results)
    async with httpx.AsyncClient(timeout=settings.http_timeout, follow_redirects=True) as client:
        results = await asyncio.gather(
            _search_arxiv(client, query, per_source),
            _search_semantic_scholar(client, query, per_source),
            return_exceptions=True,
        )

    lists: list[list[Source]] = []
    for name, result in zip(("arXiv", "Semantic Scholar"), results, strict=True):
        if isinstance(result, BaseException):
            logger.warning(f"{name} search failed: {result}")
        else:
            lists.append(result)

    # Interleave so both databases are represented: a1, s1, a2, s2, ...
    papers: list[Source] = [p for group in _zip_longest(lists) for p in group]
    if papers:
        return papers[:num_results]

    try:
        return await asyncio.to_thread(_ddgs_papers, query, num_results)
    except Exception as e:
        logger.error(f"Academic DuckDuckGo fallback failed: {e}")
        return []


def _zip_longest(lists: list[list[Source]]) -> list[list[Source]]:
    longest: int = max((len(lst) for lst in lists), default=0)
    return [[lst[i] for lst in lists if i < len(lst)] for i in range(longest)]


# =========================================================================
# Combining, numbering, formatting
# =========================================================================

def number_sources(sources: list[Source]) -> list[Source]:
    """De-duplicate by URL and assign citation numbers 1..n."""
    seen: set[str] = set()
    unique: list[Source] = []
    for src in sources:
        key: str = src.url.rstrip("/").lower()
        if not src.url or key in seen:
            continue
        seen.add(key)
        src.id = len(unique) + 1
        unique.append(src)
    return unique


async def gather_sources(topic: str, queries: list[str] | None = None) -> list[Source]:
    """
    Search the web for the topic and every sub-query, plus academic papers,
    all concurrently. Results are interleaved (best result of each query
    first), numbered, and the top pages are read.
    """
    queries = [topic] + [q for q in (queries or []) if q.lower() != topic.lower()]
    per_query: int = max(2, -(-settings.web_results // len(queries)))  # ceil division

    *web_lists, papers = await asyncio.gather(
        *(asyncio.to_thread(web_search, q, per_query) for q in queries),
        academic_search(topic, settings.paper_results),
    )
    web: list[Source] = [s for group in _zip_longest(list(web_lists)) for s in group]
    sources = number_sources(web)[:settings.web_results + 2] + papers
    sources = number_sources(sources)
    await read_top_pages(sources)
    return sources


def format_context(sources: list[Source]) -> str:
    """
    Render sources as numbered plain text for the AI prompt.
    The numbers are the citation IDs the AI must use.
    """
    if not sources:
        return "No search results were available."

    lines: list[str] = []
    for src in sources:
        label: str = "Paper" if src.kind == "paper" else "Web"
        meta: str = ", ".join(x for x in (src.origin if src.kind == "paper" else "", src.year) if x)
        lines.append(f"[{src.id}] ({label}) {src.title}" + (f" — {meta}" if meta else ""))
        lines.append(f"    URL: {src.url}")
        if src.content:
            lines.append(f"    Content (from the page): {src.content}")
        elif src.snippet:
            lines.append(f"    Content: {src.snippet[:settings.snippet_chars]}")
        lines.append("")
    return "\n".join(lines).strip()


def build_sources_markdown(sources: list[Source]) -> str:
    """Build the numbered markdown 'Sources' section appended after the AI text."""
    if not sources:
        return ""
    lines: list[str] = ["", "", "## Sources", ""]
    for src in sources:
        title: str = src.title.replace("[", "(").replace("]", ")") or src.url
        meta: list[str] = []
        if src.kind == "paper":
            meta = [x for x in (src.authors, src.origin, src.year) if x]
        line: str = f"{src.id}. [{title}]({src.url})"
        if meta:
            line += " — " + ", ".join(meta)
        lines.append(line)
    return "\n".join(lines) + "\n"
