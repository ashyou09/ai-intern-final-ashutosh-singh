# AI Research Assistant

[![CI](https://github.com/ashyou09/ai-intern-final-ashutosh-singh/actions/workflows/ci.yml/badge.svg)](https://github.com/ashyou09/ai-intern-final-ashutosh-singh/actions/workflows/ci.yml)

> An AI research tool that searches the web and academic databases in real time, streams a summary in which every claim is cited, and exports professional PDF reports. Built with FastAPI, the Model Context Protocol (MCP) and a streaming SSE frontend.

---

## Live Demo

Run locally: `http://localhost:8000`

Web: `https://ai-intern-final-ashutosh-singh.vercel.app/`

---

## Visual Showcase

<p align="center">
  <img src="demonstration/1. home.png" width="45%" alt="Home Screen" />
  <img src="demonstration/2. searching.png" width="45%" alt="Researching" />
</p>
<p align="center">
  <img src="demonstration/3. results.png" width="45%" alt="Research Results" />
  <img src="demonstration/5. pdf_preview.png" width="45%" alt="PDF Export" />
</p>

---

## Features

- **Cited summaries.** Every source gets a number. The model cites claims as `[1]`, `[2]`, and each citation links to the matching entry in the Sources list.
- **Real academic search.** The arXiv and Semantic Scholar APIs (free, no key) are queried concurrently, returning real abstracts, authors and years.
- **MCP tool integration.** Web search runs through an MCP server subprocess, with an automatic DuckDuckGo fallback.
- **Model fallback chain.** OpenRouter → Groq LLaMA 70B → Groq LLaMA 8B. If a model fails halfway through an answer, the partial text is discarded and the next model starts cleanly.
- **Real-time streaming.** Results stream token by token over Server-Sent Events, with a **Stop** button.
- **PDF and TXT export.** PDFs have a title banner, clickable links, tables and code blocks. Files are built in memory, so concurrent users never collide.
- **Safe rendering.** All AI and web content is HTML-escaped, and only `http(s)` links are rendered.
- **Tested.** A pytest suite plus ruff linting runs in GitHub Actions on Python 3.11–3.13.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.11+) |
| **AI Models** | OpenRouter (primary) · Groq (fallback) |
| **MCP Protocol** | `mcp` FastMCP server over stdio |
| **Web Search** | DuckDuckGo (`ddgs`), via MCP with a direct fallback |
| **Academic Search** | arXiv API · Semantic Scholar API (`httpx`) |
| **PDF Engine** | fpdf2 |
| **Frontend** | Vanilla HTML / CSS / JavaScript |
| **Testing** | pytest · ruff · GitHub Actions |

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                  Frontend (Browser)                  │
│   index.html · style.css · app.js (SSE client)       │
└──────────────────────────┬───────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼───────────────────────────┐
│                   FastAPI Backend                    │
│  routes.py ──► agent.py ──► prompts.py               │
│                   │                                  │
│               search.py                              │
│        ┌──────────┼─────────────────┐                │
│        │          │                 │                │
│  mcp_client.py  arXiv API   Semantic Scholar API     │
│        │                                             │
│  mcp_runner.py ──► web_search_server.py (MCP stdio)  │
│        └─ fallback: DuckDuckGo directly              │
│                                                      │
│  exporter.py (PDF/TXT in memory)                     │
│  config.py · errors.py · utils.py                    │
└──────────────────────────────────────────────────────┘
```

### Research flow

1. `search.gather_sources()` runs web search and academic search **concurrently**.
2. Results are de-duplicated by URL and numbered `[1]…[n]`.
3. The numbered sources are passed to the model, which must cite them by number.
4. The answer streams to the browser. A numbered **Sources** section is appended by the server (not the model), so every citation points to a real URL.

### MCP integration

```
search.web_search()
  └─► mcp_client.call_tool_subprocess()
        └─► spawns mcp_runner.py (subprocess, same Python interpreter)
              └─► connects to web_search_server.py via stdio
                    └─► executes the web_search tool → JSON on stdout
```

The MCP client runs in its own subprocess so that its event loop stays separate from FastAPI's.

---

## Project Structure

```
ai-intern-final-ashutosh-singh/
├── backend/
│   ├── agent.py          # Research workflow, model fallback chain, SSE events
│   ├── search.py         # Web + academic search, source numbering, context formatting
│   ├── config.py         # Centralised settings (pydantic-settings)
│   ├── errors.py         # Exceptions and error handlers ({"error": "..."})
│   ├── exporter.py       # PDF & TXT export engine (fpdf2)
│   ├── main.py           # FastAPI app: CORS, handlers, router, static files
│   ├── mcp_client.py     # MCP subprocess client
│   ├── mcp_runner.py     # MCP subprocess entry point
│   ├── prompts.py        # All prompt templates
│   ├── routes.py         # /research, /export, /health
│   └── utils.py          # Logging and request models/validators
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js            # SSE client, safe markdown renderer, export
├── mcp_servers/
│   ├── web_search_server.py    # MCP web_search tool (DuckDuckGo)
│   └── filesystem_server.py    # MCP save_research tool (standalone example)
├── tests/                # pytest suite (no network or API keys needed)
├── .github/workflows/ci.yml
├── .env.example
├── pyproject.toml
├── requirements.txt
└── requirements-dev.txt
```

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/ashyou09/ai-intern-final-ashutosh-singh.git
cd ai-intern-final-ashutosh-singh
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Then add at least one API key to `.env`.

> **Get free API keys:**
> - OpenRouter: [openrouter.ai](https://openrouter.ai) (many free models available)
> - Groq: [console.groq.com](https://console.groq.com) (free tier, very fast)

### 5. Run the server

```bash
uvicorn backend.main:app --reload --port 8000
```

Open **http://localhost:8000** in your browser.

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest -q
ruff check backend mcp_servers tests
```

The tests mock every search engine and AI model, so they need no network or API keys.

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the frontend UI |
| `/research` | POST (SSE) | Streams a cited research summary for a topic |
| `/export` | POST | Returns the content as a `.pdf` or `.txt` download |
| `/health` | GET | Health check and list of configured models |

### `POST /research`

```json
{ "topic": "quantum computing" }
```

The response is `text/event-stream`. Each event is a `data:` line containing JSON:

```json
{"type": "status",  "stage": "search", "message": "Searching the web and academic databases..."}
{"type": "status",  "stage": "analyze", "message": "Analyzing 10 sources..."}
{"type": "status",  "stage": "write", "message": "Writing summary with openai/gpt-oss-120b:free..."}
{"type": "content", "text": "# Quantum Computing\n\n## Overview\nQuantum computers ... [1]"}
{"type": "reset",   "message": "The model stopped mid-answer; retrying with a fallback model."}
{"type": "done",    "sources": [{"id": 1, "title": "...", "url": "https://...", "kind": "web"}], "model": "...", "topic": "..."}
{"type": "error",   "message": "All AI models failed. ..."}
```

`reset` is only sent when a model fails after it has started answering. The client should discard the text streamed so far.

### `POST /export`

```json
{ "content": "# Title\n\n## Overview\n...", "filename": "quantum_computing", "format": "pdf" }
```

### Errors

Every error has the shape `{"error": "<message>"}`. For example, an empty topic returns `422 {"error": "Topic cannot be empty."}`.

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes* | — | OpenRouter API key (primary model) |
| `GROQ_API_KEY` | Yes* | — | Groq API key (fallback models) |
| `PRIMARY_MODEL` | No | `openai/gpt-oss-120b:free` | OpenRouter model ID |
| `FALLBACK_MODEL` | No | `llama-3.3-70b-versatile` | First Groq fallback |
| `FALLBACK_MODEL_2` | No | `llama-3.1-8b-instant` | Second Groq fallback |
| `MAX_TOKENS` | No | `2000` | Max tokens per AI response |
| `WEB_RESULTS` | No | `6` | Number of web results |
| `PAPER_RESULTS` | No | `4` | Number of academic papers |
| `CORS_ORIGINS` | No | `*` | Comma-separated allowed origins |

> *At least one of `OPENROUTER_API_KEY` or `GROQ_API_KEY` must be set.

---

## Security

- `.env` is gitignored, and secrets are read only through `backend/config.py`.
- AI output and web content are HTML-escaped before rendering. Only `http(s)` links are allowed.
- Export filenames are sanitised, which prevents path traversal and header injection.
- CORS origins are configurable. Set `CORS_ORIGINS` to your domain in production.

---

## Author

**Ashutosh Singh**
GitHub: [@ashyou09](https://github.com/ashyou09)
