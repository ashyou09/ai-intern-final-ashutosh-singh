import asyncio
import json
from types import SimpleNamespace

import pytest

import backend.agent as agent
from backend.search import Source, number_sources


def _chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class FakeStream:
    def __init__(self, parts, fail_after=None):
        self.parts, self.fail_after = parts, fail_after

    async def __aiter__(self):
        for i, part in enumerate(self.parts):
            if self.fail_after is not None and i == self.fail_after:
                raise RuntimeError("connection dropped")
            yield _chunk(part)


def _model(name, stream=None, error=None):
    async def create(**kwargs):
        if error:
            raise error
        return stream

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return agent.ModelOption("Fake", name, client)


def _run(topic="topic"):
    async def collect():
        return [json.loads(e.removeprefix("data: ")) async for e in agent.run_research_workflow(topic)]
    return asyncio.run(collect())


@pytest.fixture(autouse=True)
def fake_sources(monkeypatch):
    async def gather(topic):
        return number_sources([Source("Web A", "https://a.com", "s", "web")])
    monkeypatch.setattr(agent, "gather_sources", gather)


def test_success_streams_content_then_sources(monkeypatch):
    monkeypatch.setattr(agent, "get_model_chain", lambda: [_model("m1", FakeStream(["Hello ", "[1]"]))])
    events = _run()
    types = [e["type"] for e in events]
    assert types[-1] == "done"
    text = "".join(e["text"] for e in events if e["type"] == "content")
    assert text.startswith("Hello [1]")
    assert "1. [Web A](https://a.com)" in text
    assert events[-1]["model"] == "m1"
    assert events[-1]["sources"][0]["url"] == "https://a.com"


def test_mid_stream_failure_sends_reset_and_falls_back(monkeypatch):
    monkeypatch.setattr(agent, "get_model_chain", lambda: [
        _model("m1", FakeStream(["partial ", "never"], fail_after=1)),
        _model("m2", FakeStream(["full answer"])),
    ])
    events = _run()
    types = [e["type"] for e in events]
    assert "reset" in types
    after_reset = events[types.index("reset") + 1:]
    text = "".join(e["text"] for e in after_reset if e["type"] == "content")
    assert text.startswith("full answer")
    assert events[-1]["type"] == "done" and events[-1]["model"] == "m2"


def test_failure_before_streaming_does_not_reset(monkeypatch):
    monkeypatch.setattr(agent, "get_model_chain", lambda: [
        _model("m1", error=RuntimeError("401")),
        _model("m2", FakeStream(["ok"])),
    ])
    types = [e["type"] for e in _run()]
    assert "reset" not in types
    assert types[-1] == "done"


def test_empty_response_falls_back(monkeypatch):
    monkeypatch.setattr(agent, "get_model_chain", lambda: [
        _model("m1", FakeStream([])),
        _model("m2", FakeStream(["ok"])),
    ])
    assert _run()[-1]["model"] == "m2"


def test_all_models_fail(monkeypatch):
    monkeypatch.setattr(agent, "get_model_chain", lambda: [_model("m1", error=RuntimeError("down"))])
    events = _run()
    assert events[-1]["type"] == "error"


def test_no_models_configured(monkeypatch):
    monkeypatch.setattr(agent, "get_model_chain", lambda: [])
    events = _run()
    assert events[-1] == {"type": "error", "message": events[-1]["message"]}
    assert "API_KEY" in events[-1]["message"]


def test_search_failure_still_produces_summary(monkeypatch):
    async def broken(topic):
        raise RuntimeError("network down")
    monkeypatch.setattr(agent, "gather_sources", broken)
    monkeypatch.setattr(agent, "get_model_chain", lambda: [_model("m1", FakeStream(["text"]))])
    events = _run()
    assert events[-1]["type"] == "done"
    assert events[-1]["sources"] == []


def test_model_chain_skips_placeholder_keys(monkeypatch):
    monkeypatch.setattr(agent.settings, "openrouter_api_key", "your-openrouter-key")
    monkeypatch.setattr(agent.settings, "groq_api_key", "gsk_real")
    chain = agent.get_model_chain()
    assert [m.provider for m in chain] == ["Groq", "Groq"]
