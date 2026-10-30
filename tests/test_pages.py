import asyncio

import httpx
import pytest

import backend.pages as pages
from backend.pages import extract_text, fetch_page_text, read_top_pages
from backend.search import Source, format_context

ARTICLE = """<html><head><title>T</title><style>.x{}</style><script>var a = 1;</script></head>
<body>
  <nav><a href="/">Home</a> <a href="/about">About us and other navigation links here</a></nav>
  <header>Site header that is long enough to count as a block of text</header>
  <main>
    <h1>Short</h1>
    <p>Quantum computers use qubits, which can represent zero and one at the same time.</p>
    <p>Error correction is the main obstacle to building large machines &amp; scaling them.</p>
    <p>Quantum computers use qubits, which can represent zero and one at the same time.</p>
  </main>
  <footer>Copyright notice and a long list of footer links that should be ignored</footer>
</body></html>"""


def test_extract_text_keeps_main_content_only():
    text = extract_text(ARTICLE)
    assert text.splitlines() == [
        "Quantum computers use qubits, which can represent zero and one at the same time.",
        "Error correction is the main obstacle to building large machines & scaling them.",
    ]


def test_extract_text_truncates():
    assert len(extract_text(ARTICLE, max_chars=20)) == 20


def test_extract_text_survives_broken_html():
    assert "unclosed paragraph that is still long enough" in extract_text(
        "<p>unclosed paragraph that is still long enough<div><span>")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1", "[::1]"])
def test_private_hosts_are_blocked(host):
    assert asyncio.run(pages.is_safe_url(f"http://{host}/admin")) is False


def test_non_http_schemes_are_blocked():
    assert asyncio.run(pages.is_safe_url("file:///etc/passwd")) is False
    assert asyncio.run(pages.is_safe_url("ftp://example.com/x")) is False


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def all_hosts_public(monkeypatch):
    async def safe(url):
        return url.startswith("https://")
    monkeypatch.setattr(pages, "is_safe_url", safe)


def test_fetch_page_text(all_hosts_public):
    def handler(request):
        return httpx.Response(200, html=ARTICLE)

    async def run():
        async with _client(handler) as client:
            return await fetch_page_text(client, "https://a.com", 5000)
    assert "Error correction" in asyncio.run(run())


def test_fetch_page_text_follows_redirect_and_checks_every_hop(all_hosts_public):
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "http://internal/secret"})
        return httpx.Response(200, html=ARTICLE)

    async def run():
        async with _client(handler) as client:
            return await fetch_page_text(client, "https://a.com/start", 5000)
    assert asyncio.run(run()) == ""   # redirect target is not https → blocked


def test_fetch_page_text_ignores_non_html(all_hosts_public):
    def handler(request):
        return httpx.Response(200, content=b"%PDF-1.4", headers={"content-type": "application/pdf"})

    async def run():
        async with _client(handler) as client:
            return await fetch_page_text(client, "https://a.com/file.pdf", 5000)
    assert asyncio.run(run()) == ""


def test_read_top_pages_fills_web_sources_only(monkeypatch):
    async def fake_fetch(client, url, max_chars):
        return "" if "broken" in url else f"text of {url}"
    monkeypatch.setattr(pages, "fetch_page_text", fake_fetch)

    sources = [
        Source("A", "https://a.com", "", "web", id=1),
        Source("Broken", "https://broken.com", "", "web", id=2),
        Source("P", "https://arxiv.org/1", "", "paper", id=3),
        Source("C", "https://c.com", "", "web", id=4),
    ]
    read = asyncio.run(read_top_pages(sources, limit=2))
    assert read == 1
    assert [s.content for s in sources] == ["text of https://a.com", "", "", ""]

    context = format_context(sources)
    assert "Content (from the page): text of https://a.com" in context
    assert sources[0].to_dict()["read"] is True and "content" not in sources[0].to_dict()
