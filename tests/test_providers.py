import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import backend.agent as agent
from backend.providers import PROVIDERS, UserLLM, describe_error
from backend.search import Source, number_sources

KEY = "sk-test-1234567890"


def test_user_llm_defaults_to_preset_model():
    llm = UserLLM(provider="openai", api_key=KEY)
    option = llm.to_option()
    assert option.model == PROVIDERS["openai"].default_model
    assert option.user_supplied is True
    assert str(option.client.base_url).startswith("https://api.openai.com/v1")


def test_user_llm_key_is_hidden_in_repr():
    llm = UserLLM(provider="groq", api_key=KEY)
    assert KEY not in repr(llm)
    assert KEY not in str(llm.model_dump())


@pytest.mark.parametrize("data, message", [
    ({"provider": "nope", "api_key": KEY}, "Unknown provider"),
    ({"provider": "openai", "api_key": "short"}, "does not look valid"),
    ({"provider": "openai", "api_key": "sk key with spaces"}, "does not look valid"),
    ({"provider": "openai", "api_key": KEY, "model": "gpt 4; rm -rf"}, "invalid characters"),
    ({"provider": "custom", "api_key": KEY, "model": "m", "base_url": "http://x.com"}, "https://"),
    ({"provider": "custom", "api_key": KEY, "base_url": "https://x.com/v1"}, "model name"),
])
def test_user_llm_validation(data, message):
    with pytest.raises(ValidationError, match=message):
        UserLLM(**data)


def test_base_url_is_ignored_for_presets():
    llm = UserLLM(provider="groq", api_key=KEY, base_url="https://evil.example")
    assert llm.base_url == ""


def test_describe_error_never_includes_provider_message():
    exc = Exception("Incorrect API key provided: sk-abc***xyz")
    exc.status_code = 401
    assert describe_error(exc) == "the API key was rejected (401)"
    assert describe_error(Exception("boom")) == "the request failed"


def test_providers_endpoint(client):
    data = client.get("/providers").json()
    ids = [p["id"] for p in data]
    assert ids[:2] == ["openrouter", "groq"] and "custom" in ids
    assert all("base_url" not in p for p in data)


def test_research_rejects_invalid_user_llm(client):
    resp = client.post("/research", json={"topic": "x", "llm": {"provider": "openai", "api_key": "bad"}})
    assert resp.status_code == 422
    assert resp.json() == {"error": "The API key does not look valid."}


# --- agent behaviour with a user-supplied model ---

def _chunk(text):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class _Stream:
    async def __aiter__(self):
        yield _chunk("server answer")


def _client(error=None):
    async def create(**kwargs):
        if error:
            raise error
        return _Stream()
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _events(user_llm):
    async def collect():
        return [json.loads(e[6:]) async for e in agent.run_research_workflow("t", user_llm)]
    return asyncio.run(collect())


@pytest.fixture(autouse=True)
def no_search(monkeypatch):
    async def gather(topic, queries=None):
        return number_sources([Source("A", "https://a.com", "", "web")])
    monkeypatch.setattr(agent, "gather_sources", gather)


def test_user_model_is_tried_first_and_failure_is_reported(monkeypatch):
    rejected = Exception("Incorrect API key provided: sk-abc")
    rejected.status_code = 401
    user_llm = UserLLM(provider="openai", api_key=KEY)
    monkeypatch.setattr(UserLLM, "to_option",
                        lambda self: agent.ModelOption("OpenAI", "gpt", _client(rejected), user_supplied=True))
    monkeypatch.setattr(agent, "get_model_chain", lambda: [agent.ModelOption("Groq", "llama", _client())])

    events = _events(user_llm)
    notices = [e["message"] for e in events if e["type"] == "notice"]
    assert notices == ["Your OpenAI model failed: the API key was rejected (401); using the server's models instead."]
    assert events[-1]["type"] == "done" and events[-1]["model"] == "llama"
    assert "sk-abc" not in json.dumps(events)


def test_user_model_alone_works_without_server_keys(monkeypatch):
    monkeypatch.setattr(UserLLM, "to_option",
                        lambda self: agent.ModelOption("OpenAI", "gpt", _client(), user_supplied=True))
    monkeypatch.setattr(agent, "get_model_chain", lambda: [])
    events = _events(UserLLM(provider="openai", api_key=KEY))
    assert events[-1]["model"] == "gpt"


def test_private_custom_base_url_is_skipped(monkeypatch):
    monkeypatch.setattr(agent, "get_model_chain", lambda: [])
    llm = UserLLM(provider="custom", api_key=KEY, model="m", base_url="https://127.0.0.1/v1")
    events = _events(llm)
    assert any(e["type"] == "notice" and "custom base URL" in e["message"] for e in events)
    assert events[-1]["type"] == "error"
