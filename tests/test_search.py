import asyncio

import backend.search as search
from backend.search import (
    Source,
    build_sources_markdown,
    format_context,
    number_sources,
    parse_arxiv_feed,
    parse_semantic_scholar,
)

ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All
      You Need</title>
    <summary>  The dominant sequence transduction models
      are based on recurrent networks. </summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <author><name>Niki Parmar</name></author>
    <author><name>Jakob Uszkoreit</name></author>
  </entry>
  <entry>
    <id></id>
    <title>Entry without a URL is skipped</title>
  </entry>
</feed>"""


def test_parse_arxiv_feed():
    papers = parse_arxiv_feed(ARXIV_FEED)
    assert len(papers) == 1
    p = papers[0]
    assert p.title == "Attention Is All You Need"
    assert p.url == "https://arxiv.org/abs/1706.03762v7"
    assert p.snippet == "The dominant sequence transduction models are based on recurrent networks."
    assert p.year == "2017"
    assert p.authors == "Ashish Vaswani, Noam Shazeer, Niki Parmar et al."
    assert p.kind == "paper" and p.origin == "arXiv"


def test_parse_semantic_scholar():
    payload = {"data": [
        {"title": "BERT", "url": "https://www.semanticscholar.org/paper/1", "abstract": None,
         "year": 2019, "venue": "NAACL", "authors": [{"name": "Jacob Devlin"}]},
        {"title": "No URL", "url": None},
    ]}
    papers = parse_semantic_scholar(payload)
    assert [p.title for p in papers] == ["BERT"]
    assert papers[0].origin == "NAACL"
    assert papers[0].year == "2019"
    assert papers[0].snippet == ""


def test_parse_semantic_scholar_handles_missing_data():
    assert parse_semantic_scholar({}) == []
    assert parse_semantic_scholar({"data": None}) == []


def test_number_sources_dedupes_and_numbers():
    sources = number_sources([
        Source("A", "https://a.com/x", "", "web"),
        Source("A again", "https://A.com/x/", "", "web"),
        Source("No URL", "", "", "web"),
        Source("B", "https://b.com", "", "paper"),
    ])
    assert [(s.id, s.title) for s in sources] == [(1, "A"), (2, "B")]


def test_format_context_lists_numbered_sources():
    sources = number_sources([
        Source("Web page", "https://a.com", "snippet text", "web"),
        Source("Paper", "https://arxiv.org/abs/1", "abstract", "paper", "arXiv", "2020"),
    ])
    context = format_context(sources)
    assert "[1] (Web) Web page" in context
    assert "[2] (Paper) Paper — arXiv, 2020" in context
    assert "URL: https://arxiv.org/abs/1" in context


def test_format_context_without_sources():
    assert format_context([]) == "No search results were available."


def test_build_sources_markdown():
    sources = number_sources([
        Source("Title [with] brackets", "https://a.com", "", "web"),
        Source("Paper", "https://arxiv.org/abs/1", "", "paper", "arXiv", "2020", "A, B"),
    ])
    md = build_sources_markdown(sources)
    assert "## Sources" in md
    assert "1. [Title (with) brackets](https://a.com)" in md
    assert "2. [Paper](https://arxiv.org/abs/1) — A, B, arXiv, 2020" in md
    assert build_sources_markdown([]) == ""


def test_academic_search_interleaves_both_apis(monkeypatch):
    async def arxiv(client, q, n):
        return [Source(f"a{i}", f"https://arxiv.org/{i}", "", "paper") for i in range(3)]

    async def s2(client, q, n):
        return [Source(f"s{i}", f"https://s2.org/{i}", "", "paper") for i in range(3)]

    monkeypatch.setattr(search, "_search_arxiv", arxiv)
    monkeypatch.setattr(search, "_search_semantic_scholar", s2)
    papers = asyncio.run(search.academic_search("q", 4))
    assert [p.title for p in papers] == ["a0", "s0", "a1", "s1"]


def test_academic_search_falls_back_to_duckduckgo(monkeypatch):
    async def failing(client, q, n):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(search, "_search_arxiv", failing)
    monkeypatch.setattr(search, "_search_semantic_scholar", failing)
    monkeypatch.setattr(search, "_ddgs_text", lambda q, n: [
        {"title": "DDG paper", "href": "https://example.org/p", "body": "b"},
    ])
    papers = asyncio.run(search.academic_search("q", 4))
    assert [p.title for p in papers] == ["DDG paper"]


def test_web_search_falls_back_when_mcp_fails(monkeypatch):
    def broken_mcp(**kwargs):
        raise RuntimeError("no MCP")

    monkeypatch.setattr(search, "call_tool_subprocess", broken_mcp)
    monkeypatch.setattr(search, "_ddgs_text", lambda q, n: [
        {"title": "T", "href": "https://t.com", "body": "B"},
    ])
    results = search.web_search("q", 3)
    assert [(r.title, r.url, r.snippet) for r in results] == [("T", "https://t.com", "B")]


def test_web_search_treats_mcp_error_payload_as_failure(monkeypatch):
    monkeypatch.setattr(search, "call_tool_subprocess",
                        lambda **kw: '[{"error": "Search failed: ratelimit"}]')
    monkeypatch.setattr(search, "_ddgs_text", lambda q, n: [])
    assert search.web_search("q", 3) == []


def test_web_search_uses_mcp_result(monkeypatch):
    monkeypatch.setattr(search, "call_tool_subprocess",
                        lambda **kw: '[{"title": "Error handling in Rust", "url": "https://r.com", "snippet": "s"}]')
    results = search.web_search("q", 3)
    assert [r.title for r in results] == ["Error handling in Rust"]


def test_gather_sources_searches_every_query_and_interleaves(monkeypatch):
    calls = []

    def fake_web(query, n):
        calls.append((query, n))
        return [Source(f"{query}-{i}", f"https://{query.replace(' ', '')}.com/{i}", "", "web") for i in range(n)]

    async def fake_papers(query, n):
        return [Source("paper", "https://arxiv.org/1", "", "paper")]

    async def no_pages(sources):
        return 0

    monkeypatch.setattr(search, "web_search", fake_web)
    monkeypatch.setattr(search, "academic_search", fake_papers)
    monkeypatch.setattr(search, "read_top_pages", no_pages)
    monkeypatch.setattr(search.settings, "web_results", 6)

    sources = asyncio.run(search.gather_sources("topic", ["sub one", "TOPIC"]))
    assert [q for q, _ in calls] == ["topic", "sub one"]          # duplicate of the topic is skipped
    assert [s.title for s in sources[:4]] == ["topic-0", "sub one-0", "topic-1", "sub one-1"]
    assert sources[-1].kind == "paper"
    assert [s.id for s in sources] == list(range(1, len(sources) + 1))
