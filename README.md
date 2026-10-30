# AI Research Assistant

[![CI](https://github.com/ashyou09/ai-intern-final-ashutosh-singh/actions/workflows/ci.yml/badge.svg)](https://github.com/ashyou09/ai-intern-final-ashutosh-singh/actions/workflows/ci.yml)

> An AI research agent that plans its own searches, reads web pages and academic papers, and streams a summary in which every claim is cited. Reports export to PDF, Markdown or plain text. Built with FastAPI, the Model Context Protocol (MCP) and a streaming SSE frontend. It works with the server's free models or with your own API key.

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

### Research
- **Planned searches.** The model splits your topic into 2–3 focused sub-queries (background, recent developments, challenges, applications), and every one is searched in parallel.
- **Full-page reading.** The top web results are downloaded and their main text extracted, so summaries are built from real content rather than 200-character snippets.
- **Real academic search.** The arXiv and Semantic Scholar APIs (free, no key) return real abstracts, authors and years.
- **Cited summaries.** Every source gets a number. The model cites claims as `[1]`, `[2]`, and each citation links to the matching source.
- **MCP tool integration.** Web search runs through an MCP server subprocess, with an automatic DuckDuckGo fallback.

### Models
- **Fallback chain:** your own key (if set) → OpenRouter → Groq LLaMA 70B → Groq LLaMA 8B. If a model fails halfway through an answer, the partial text is discarded and the next model starts cleanly.
- **Bring your own key.** If the free models are busy, paste a key for OpenRouter, Groq, OpenAI, Google Gemini, DeepSeek, Mistral or any OpenAI-compatible API in **Settings**. The key stays in your browser.

### Interface
- Token-by-token streaming with a **Stop** button, live progress steps, and chips showing the planned queries
- Result stats (model, sources, pages read, reading time) and "Paper" / "Read in full" badges
- **Research history** saved in the browser; reopen a past report instantly
- Example topics, a `/` keyboard shortcut, a mobile layout and reduced-motion support
- Export to **PDF** (title banner, clickable links, page numbers), **Markdown** or **plain text**, or **Copy** to the clipboard

### Production
- Rate limiting per client, caching of sources for repeated topics, and SSRF-safe page fetching
- HTML-escaped rendering (no XSS), and API keys never logged
- Docker image with a health check, plus 95 tests and CI on Python 3.11–3.13

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.11+) |
| **AI Models** | Any OpenAI-compatible API: OpenRouter and Groq on the server, or the user's own key |
| **MCP Protocol** | `mcp` FastMCP server over stdio |
| **Web Search** | DuckDuckGo (`ddgs`), via MCP with a direct fallback |
| **Academic Search** | arXiv API · Semantic Scholar API (`httpx`) |
| **PDF Engine** | fpdf2 |
| **Frontend** | Vanilla HTML / CSS / JavaScript |
| **Testing / Ops** | pytest · ruff · GitHub Actions · Docker |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      Frontend (Browser)                      │
│  index.html · style.css · app.js                             │
│  SSE client · safe markdown renderer · settings · history    │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP / SSE
┌──────────────────────────────▼───────────────────────────────┐
│                       FastAPI Backend                        │
│  routes.py ── ratelimit.py                                   │
│     │                                                        │
│  agent.py ── providers.py (OpenAI-compatible model chain)    │
│     │     └─ cache.py (sources per topic, 1 h)               │
│     │                                                        │
│  search.py ──┬── mcp_client.py ─► mcp_runner.py ─► MCP server│
│              │      └─ fallback: DuckDuckGo directly         │
│              ├── arXiv API · Semantic Scholar API            │
│              └── pages.py (read top pages, SSRF-safe)        │
│                                                              │
│  exporter.py (PDF / MD / TXT in memory)                      │
│  config.py · errors.py · utils.py · prompts.py               │
└──────────────────────────────────────────────────────────────┘
```

### Research flow

1. **Plan.** `agent.plan_queries()` asks the first available model for 2–3 sub-queries. This step is best-effort: the topic itself is always searched.
2. **Search.** `search.gather_sources()` searches the web for every query and searches arXiv and Semantic Scholar, all concurrently.
3. **Read.** `pages.read_top_pages()` downloads the top 3 web results and extracts their main text.
4. **Number.** Sources are de-duplicated by URL and numbered `[1]…[n]`, then cached for an hour.
5. **Write.** The model streams a summary that cites those numbers. If a model fails, the next one in the chain takes over.
6. **Cite.** The server (not the model) appends a numbered **Sources** section, so every citation points to a real URL.

### MCP integration

```
search.web_search()
  └─► mcp_client.call_tool_subprocess()
        └─► spawns mcp_runner.py (subprocess, same Python interpreter)
              └─► connects to web_search_server.py via stdio
                    └─► executes the web_search tool → JSON on stdout
```

The MCP client runs in its own subprocess so that its event loop stays separate from FastAPI's. If MCP fails, it is paused for 5 minutes and DuckDuckGo is called directly.

---

## Project Structure

```
ai-intern-final-ashutosh-singh/
├── backend/
│   ├── agent.py          # Workflow: plan → search → write, SSE events, model fallback
│   ├── providers.py      # Provider presets, server model chain, bring-your-own-key
│   ├── search.py         # Web + academic search, numbering, prompt context
│   ├── pages.py          # Reads top result pages (HTML → text, SSRF protection)
│   ├── cache.py          # TTL/LRU cache for sources
│   ├── ratelimit.py      # Per-client sliding-window rate limiting
│   ├── exporter.py       # PDF / Markdown / TXT export (fpdf2)
│   ├── prompts.py        # All prompt templates
│   ├── routes.py         # /research, /export, /providers, /health
│   ├── config.py         # Settings from .env (pydantic-settings)
│   ├── errors.py         # Error handlers ({"error": "..."})
│   ├── utils.py          # Logging and request models
│   ├── mcp_client.py     # MCP subprocess client
│   ├── mcp_runner.py     # MCP subprocess entry point
│   └── main.py           # FastAPI app: CORS, handlers, router, static files
├── frontend/             # index.html · style.css · app.js
├── mcp_servers/
│   ├── web_search_server.py    # MCP web_search tool (DuckDuckGo)
│   └── filesystem_server.py    # MCP save_research tool (standalone example)
├── tests/                # pytest suite (no network or API keys needed)
├── .github/workflows/ci.yml    # lint + tests (3.11–3.13) + Docker smoke test
├── Dockerfile · docker-compose.yml
├── .env.example
├── pyproject.toml · requirements.txt · requirements-dev.txt
└── README.md
```

---

## Setup & Installation

### Option A: Docker (one command)

```bash
cp .env.example .env        # then add at least one API key
docker compose up --build
```

Open **http://localhost:8000**.

### Option B: Python

```bash
git clone https://github.com/ashyou09/ai-intern-final-ashutosh-singh.git
cd ai-intern-final-ashutosh-singh

python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then add at least one API key
uvicorn backend.main:app --reload --port 8000
```

Open **http://localhost:8000**.

> **Get free API keys:**
> - OpenRouter: [openrouter.ai](https://openrouter.ai) (many free models available)
> - Groq: [console.groq.com](https://console.groq.com) (free tier, very fast)
>
> No server keys? The app still works if each visitor adds their own key in **Settings**.

---

## Using your own API key

Click the **Server models** badge in the top-right corner to open **AI model settings**:

1. Choose a provider: OpenRouter, Groq, OpenAI, Google Gemini, DeepSeek, Mistral, or **Custom** (any OpenAI-compatible base URL).
2. Paste your API key and, optionally, a model name.
3. Optionally tick **Remember on this device**. Otherwise the key lasts only for this tab.

Your model is tried first, and the server models are the backup. If your key fails (for example, it's invalid or out of credit), a notice explains why and the server models take over.

**Privacy:** the key is stored only in your browser and sent with each research request. The server uses it for that request only and never stores, logs or returns it. Provider error messages, which can contain part of a key, are never forwarded.

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
| `/research` | POST (SSE) | Streams a cited research summary (rate-limited) |
| `/export` | POST | Returns the content as `.pdf`, `.md` or `.txt` |
| `/providers` | GET | Providers available for bring-your-own-key |
| `/health` | GET | Health check, configured models and MCP status |

### `POST /research`

```json
{
  "topic": "quantum computing",
  "llm": { "provider": "openai", "api_key": "sk-...", "model": "gpt-4o-mini" }
}
```

`llm` is optional. Without it, the server models are used. For `"provider": "custom"`, also send `base_url` (an https URL) and `model`.

The response is `text/event-stream`. Each event is a `data:` line containing JSON:

| Event | Fields | Meaning |
|-------|--------|---------|
| `status` | `stage` (`plan`/`search`/`analyze`/`write`), `message`, `cached?` | Progress |
| `plan` | `queries` | The sub-queries that will be searched |
| `content` | `text` | A chunk of the Markdown summary |
| `notice` | `message` | Non-fatal information, such as "your key was rejected (401); using the server's models" |
| `reset` | `message` | A model failed mid-answer; discard the text received so far |
| `done` | `sources`, `model`, `topic` | Finished. `sources` is `[{id, title, url, kind, origin, year, authors, read}]` |
| `error` | `message` | Failed |

### `POST /export`

```json
{ "content": "# Title\n\n## Overview\n...", "filename": "quantum_computing", "format": "pdf" }
```

`format` is `pdf`, `md` or `txt`.

### Errors

Every error has the shape `{"error": "<message>"}`:

| Status | When |
|--------|------|
| `422` | Invalid input, e.g. `{"error": "Topic cannot be empty."}` |
| `429` | Rate limit reached. A `Retry-After` header is included |
| `500` | Export failed or an unexpected error |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | OpenRouter key (primary server model)* |
| `GROQ_API_KEY` | — | Groq key (fallback server models)* |
| `PRIMARY_MODEL` | `openai/gpt-oss-120b:free` | OpenRouter model |
| `FALLBACK_MODEL` | `llama-3.3-70b-versatile` | First Groq fallback |
| `FALLBACK_MODEL_2` | `llama-3.1-8b-instant` | Second Groq fallback |
| `MAX_TOKENS` | `2000` | Max tokens per summary |
| `PLAN_QUERIES` | `true` | Let the model plan sub-queries |
| `MAX_SUBQUERIES` | `3` | Number of planned sub-queries |
| `WEB_RESULTS` | `6` | Web results kept |
| `PAPER_RESULTS` | `4` | Academic papers kept |
| `PAGES_TO_READ` | `3` | Top web pages read in full (`0` = snippets only) |
| `PAGE_CHARS` | `2500` | Max characters kept per page |
| `CACHE_TTL` | `3600` | Seconds to reuse a topic's sources (`0` = off) |
| `USE_MCP` | `true` | Search through the MCP server (`false` = DuckDuckGo directly) |
| `RATE_LIMIT_PER_MINUTE` | `5` | Research requests per client per minute (`0` = unlimited) |
| `RATE_LIMIT_PER_HOUR` | `40` | Research requests per client per hour |
| `TRUST_PROXY` | `false` | Use `X-Forwarded-For` for the client IP (automatic on Vercel) |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins |

> *Without server keys, visitors must add their own key in Settings.

---

## Deployment Notes

- **Vercel / serverless.** Each MCP search starts a Python subprocess, which is slow on serverless hosts. Set `USE_MCP=false` there; DuckDuckGo is then called directly. `/health` shows `"mcp": "enabled" | "disabled" | "paused"`.
- **Behind a reverse proxy** (nginx, Render, Fly.io…), set `TRUST_PROXY=true` so rate limits apply per visitor rather than to the proxy's IP.
- **Multiple instances.** The cache and rate limits are held in memory per process. That is fine for one instance; use a shared store such as Redis if you scale out.
- **Production CORS.** Set `CORS_ORIGINS=https://your-domain.com`.

---

## Security

- `.env` is gitignored, and secrets are read only through `backend/config.py`.
- User API keys are held in `SecretStr`, used once and never logged or stored.
- AI output and web content are HTML-escaped before rendering. Only `http(s)` links are allowed.
- Page reading and custom provider URLs only reach public IPs (no SSRF to `localhost`, private networks or cloud metadata endpoints).
- Export filenames are sanitised, which prevents path traversal and header injection.
- Per-client rate limits protect the shared API quota.

---

## Author

**Ashutosh Singh**
GitHub: [@ashyou09](https://github.com/ashyou09)
