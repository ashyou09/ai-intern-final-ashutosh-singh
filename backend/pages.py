"""
Page reader — fetches the top web results and extracts their main text.

Search snippets are only ~200 characters, which limits how deep a summary
can be. This module downloads the top few result pages concurrently and
extracts readable text so the model has real content to work with.

Safety:
  - Only http(s) URLs on public IP addresses are fetched (no localhost,
    private networks or cloud metadata endpoints — prevents SSRF).
  - Redirects are followed manually so every hop is checked.
  - Downloads are capped in size and time; failures are silently skipped.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from backend.config import settings
from backend.utils import logger

MAX_DOWNLOAD_BYTES: int = 2_000_000
MAX_REDIRECTS: int = 3
USER_AGENT: str = "Mozilla/5.0 (compatible; AIResearchAssistant/1.1; +https://github.com/ashyou09/ai-intern-final-ashutosh-singh)"

# Elements whose text is never part of the main content
_SKIP_TAGS: set[str] = {
    "script", "style", "noscript", "svg", "nav", "header", "footer",
    "aside", "form", "button", "iframe", "template", "select",
}
# Elements that end a block of text
_BLOCK_TAGS: set[str] = {
    "p", "div", "section", "article", "main", "li", "ul", "ol", "br",
    "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th", "blockquote", "pre",
}
_MIN_BLOCK_CHARS: int = 40   # shorter blocks are usually menus, buttons, captions


class _TextExtractor(HTMLParser):
    """Collects visible text blocks, skipping navigation and scripts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._current: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._current.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self._current)).strip()
        self._current = []
        if len(text) >= _MIN_BLOCK_CHARS:
            self.blocks.append(text)

    def close(self) -> None:
        super().close()
        self._flush()


def extract_text(html: str, max_chars: int | None = None) -> str:
    """Extract the readable main text from an HTML document."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # malformed HTML — keep whatever was parsed
        pass

    # Drop exact duplicate blocks (cookie banners, repeated captions)
    seen: set[str] = set()
    blocks: list[str] = []
    for block in parser.blocks:
        if block not in seen:
            seen.add(block)
            blocks.append(block)

    text = "\n".join(blocks)
    return text[:max_chars] if max_chars else text


def _is_public_host(host: str) -> bool:
    """True only if every address the host resolves to is a public IP."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            return False
    return bool(infos)


async def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    return await asyncio.to_thread(_is_public_host, parsed.hostname)


async def fetch_page_text(client: httpx.AsyncClient, url: str, max_chars: int) -> str:
    """Download one page and return its extracted text ("" on any failure)."""
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if not await is_safe_url(url):
                logger.info(f"Skipping non-public URL: {url}")
                return ""
            async with client.stream("GET", url) as resp:
                if resp.is_redirect and "location" in resp.headers:
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
                    return ""
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) >= MAX_DOWNLOAD_BYTES:
                        break
                html = body.decode(resp.encoding or "utf-8", errors="replace")
                return extract_text(html, max_chars)
        return ""
    except Exception as e:
        logger.info(f"Could not read {url}: {type(e).__name__}")
        return ""


async def read_top_pages(sources: list, limit: int | None = None) -> int:
    """
    Fill `content` on the first `limit` web sources by reading their pages.
    Returns how many pages were read successfully.
    """
    limit = settings.pages_to_read if limit is None else limit
    targets = [s for s in sources if s.kind == "web"][:limit]
    if not targets:
        return 0

    async with httpx.AsyncClient(
        timeout=settings.page_timeout,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    ) as client:
        texts = await asyncio.gather(*(fetch_page_text(client, s.url, settings.page_chars) for s in targets))

    read = 0
    for src, text in zip(targets, texts, strict=True):
        if text:
            src.content = text
            read += 1
    logger.info(f"Read {read}/{len(targets)} pages")
    return read
