from types import SimpleNamespace

import pytest

import backend.agent as agent
import backend.ratelimit as ratelimit
from backend.ratelimit import SlidingWindowLimiter, client_ip


def test_sliding_window_allows_up_to_limit():
    limiter = SlidingWindowLimiter(limit=2, window=60)
    assert limiter.hit("ip", now=0) == 0
    assert limiter.hit("ip", now=10) == 0
    assert limiter.hit("ip", now=20) == pytest.approx(40)   # oldest hit expires at t=60
    assert limiter.hit("other", now=20) == 0                # limits are per client
    assert limiter.hit("ip", now=60) == 0                   # window has slid past the first hit


def test_zero_limit_disables():
    limiter = SlidingWindowLimiter(limit=0, window=60)
    assert all(limiter.hit("ip", now=i) == 0 for i in range(100))


def test_idle_clients_are_pruned():
    limiter = SlidingWindowLimiter(limit=5, window=60)
    limiter.hit("a", now=0)
    limiter.hit("b", now=100)
    assert set(limiter._hits) == {"b"}


def _request(host="1.2.3.4", forwarded=None):
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers)


def test_client_ip_ignores_forwarded_header_by_default(monkeypatch):
    monkeypatch.setattr(ratelimit.settings, "trust_proxy", False)
    monkeypatch.setattr(ratelimit.settings, "vercel", "")
    assert client_ip(_request(forwarded="9.9.9.9")) == "1.2.3.4"


@pytest.mark.parametrize("trust, vercel", [(True, ""), (False, "1")])
def test_client_ip_uses_forwarded_header_behind_proxy(monkeypatch, trust, vercel):
    monkeypatch.setattr(ratelimit.settings, "trust_proxy", trust)
    monkeypatch.setattr(ratelimit.settings, "vercel", vercel)
    assert client_ip(_request(forwarded="9.9.9.9, 10.0.0.1")) == "9.9.9.9"


def test_research_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(ratelimit.minute_limiter, "limit", 2)
    monkeypatch.setattr(agent, "get_model_chain", lambda: [])

    statuses = [client.post("/research", json={"topic": "x"}).status_code for _ in range(2)]
    assert statuses == [200, 200]

    resp = client.post("/research", json={"topic": "x"})
    assert resp.status_code == 429
    assert resp.json()["error"].startswith("Too many research requests this minute")
    assert int(resp.headers["retry-after"]) > 0


def test_other_routes_are_not_limited(client, monkeypatch):
    monkeypatch.setattr(ratelimit.minute_limiter, "limit", 1)
    assert all(client.get("/health").status_code == 200 for _ in range(5))


def test_unknown_route_uses_error_shape(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert "error" in resp.json()
