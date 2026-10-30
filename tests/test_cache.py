import asyncio
import json
from types import SimpleNamespace

import backend.agent as agent
import backend.cache as cache_module
from backend.cache import TTLCache, topic_key
from backend.search import Source, number_sources


def test_ttl_cache_expires(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])
    c = TTLCache(ttl=10)
    c.set("a", 1)
    assert c.get("a") == 1
    now[0] += 10
    assert c.get("a") is None
    assert len(c) == 0


def test_ttl_cache_evicts_least_recently_used():
    c = TTLCache(ttl=60, max_entries=2)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")          # a is now the most recently used
    c.set("c", 3)
    assert c.get("b") is None and c.get("a") == 1 and c.get("c") == 3


def test_ttl_cache_returns_copies():
    c = TTLCache(ttl=60)
    c.set("k", [1])
    c.get("k").append(2)
    assert c.get("k") == [1]


def test_zero_ttl_disables_cache():
    c = TTLCache(ttl=0)
    c.set("k", 1)
    assert c.get("k") is None


def test_topic_key_normalises():
    assert topic_key("  Quantum   Computing ") == topic_key("quantum computing")


def _chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class _Stream:
    async def __aiter__(self):
        yield _chunk("answer [1]")


def _client():
    async def create(**kwargs):
        if kwargs.get("stream"):
            return _Stream()
        msg = SimpleNamespace(content='["sub query"]')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_repeated_topic_uses_cached_sources(monkeypatch):
    calls = []

    async def gather(topic, queries=None):
        calls.append(topic)
        return number_sources([Source("A", "https://a.com", "", "web")])

    monkeypatch.setattr(agent, "gather_sources", gather)
    monkeypatch.setattr(agent, "get_model_chain", lambda: [agent.ModelOption("P", "m", _client())])

    def run(topic):
        async def collect():
            return [json.loads(e[6:]) async for e in agent.run_research_workflow(topic)]
        return asyncio.run(collect())

    first = run("Quantum computing")
    second = run("quantum   computing")
    assert calls == ["Quantum computing"]
    assert any(e.get("cached") for e in second)
    assert [e for e in second if e["type"] == "plan"] == [e for e in first if e["type"] == "plan"]
    assert second[-1]["sources"] == first[-1]["sources"]
