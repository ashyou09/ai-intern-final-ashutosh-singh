import json

import backend.agent as agent
from backend.search import Source, number_sources


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_frontend_is_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AI Research Assistant" in resp.text


def test_research_rejects_empty_topic(client):
    resp = client.post("/research", json={"topic": "   "})
    assert resp.status_code == 422
    assert resp.json() == {"error": "Topic cannot be empty."}


def test_research_rejects_long_topic(client):
    resp = client.post("/research", json={"topic": "x" * 501})
    assert resp.status_code == 422
    assert "500 characters" in resp.json()["error"]


def test_research_streams_sse(client, monkeypatch):
    async def gather(topic, queries=None):
        return number_sources([Source("A", "https://a.com", "", "web")])
    monkeypatch.setattr(agent, "gather_sources", gather)
    monkeypatch.setattr(agent, "get_model_chain", lambda: [])

    resp = client.post("/research", json={"topic": "quantum"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in resp.text.split("\n\n") if line.startswith("data: ")]
    assert events == [{"type": "error", "message": events[0]["message"]}]   # no model → fail fast, no search


def test_export_txt(client):
    resp = client.post("/export", json={"content": "# Hi\nü", "filename": "My Topic", "format": "txt"})
    assert resp.status_code == 200
    assert resp.content.decode("utf-8") == "# Hi\nü"
    assert resp.headers["content-disposition"] == 'attachment; filename="My_Topic.txt"'


def test_export_pdf(client):
    resp = client.post("/export", json={"content": "# Title\n\nBody", "filename": "t", "format": "pdf"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


def test_export_sanitizes_filename(client):
    resp = client.post("/export", json={"content": "x", "filename": '../../etc/"passwd"\r\n', "format": "txt"})
    assert resp.headers["content-disposition"] == 'attachment; filename="etcpasswd.txt"'


def test_export_rejects_unknown_format(client):
    resp = client.post("/export", json={"content": "x", "filename": "f", "format": "docx"})
    assert resp.status_code == 422


def test_export_rejects_empty_content(client):
    resp = client.post("/export", json={"content": "  ", "filename": "f", "format": "pdf"})
    assert resp.status_code == 422
    assert resp.json() == {"error": "Content cannot be empty."}
