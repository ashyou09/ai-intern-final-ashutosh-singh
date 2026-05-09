# AI Research Assistant

> An AI-powered research tool that performs real-time web and academic paper searches, synthesizes the results using large language models, and exports professional PDF reports — built with FastAPI, MCP Protocol, and a streaming SSE frontend.

---

## Live Demo

Run locally: `http://localhost:8000`

Web: `https://ai-intern-final-ashutosh-singh.vercel.app/`

---

## Features

- **Real-Time Streaming** — Results stream token-by-token directly to the browser via Server-Sent Events (SSE)
- **MCP Tool Integration** — Web search is executed via a Model Context Protocol (MCP) server subprocess, with automatic DuckDuckGo fallback
- **Dual AI Model Chain** — Tries OpenRouter (GPT) first, then falls back to Groq (LLaMA 70B → LLaMA 8B) automatically
- **Academic Paper Search** — Searches arXiv, PubMed, Semantic Scholar, and Google Scholar in parallel with web search
- **PDF Export Engine** — Generates styled PDFs with blue title banners, section headers, code-block math rendering, and clickable links
- **TXT Export** — Clean plain-text export of all research output
- **Math Rendering** — Formulas displayed in styled code blocks (frontend) and monospace Courier boxes (PDF)
- **Responsive UI** — Dark-mode glassmorphism UI with animated loading states and step-by-step progress indicators

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI (Python 3.11+) |
| **AI Models** | OpenRouter (primary) · Groq (fallback) |
| **MCP Protocol** | `fastmcp` — web search tool via stdio subprocess |
| **Web Search** | DuckDuckGo Search (via MCP + direct fallback) |
| **PDF Engine** | fpdf2 |
| **Frontend** | Vanilla HTML / CSS / JavaScript (SSE streaming) |
| **Streaming** | Server-Sent Events (SSE) |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Frontend (Browser)               │
│  index.html · style.css · app.js (SSE client)      │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼──────────────────────────────┐
│               FastAPI Backend                       │
│  routes.py  ──►  agent.py  ──►  prompts.py         │
│                     │                               │
│          ┌──────────┴──────────┐                    │
│          │                     │                    │
│    mcp_client.py          DuckDuckGo               │
│    (subprocess)            (fallback)               │
│          │                                          │
│    mcp_runner.py                                    │
│          │                                          │
│   web_search_server.py  (MCP stdio server)         │
│                                                     │
│  exporter.py  ──►  outputs/*.pdf / *.txt           │
│  config.py · errors.py · utils.py                  │
└─────────────────────────────────────────────────────┘
```

### MCP Integration Flow

```
agent.py
  └─► mcp_client.call_tool_subprocess()
        └─► spawns mcp_runner.py (subprocess)
              └─► connects to web_search_server.py via stdio
                    └─► executes web_search tool
                          └─► returns JSON result via stdout
```

The MCP server runs in a clean subprocess to isolate its event loop from FastAPI's async loop — a production-grade pattern that prevents event loop conflicts.

---

## Project Structure

```
ai-intern-final/
├── backend/
│   ├── __init__.py
│   ├── agent.py          # AI orchestration, MCP calls, streaming workflow
│   ├── config.py         # Centralised env-var settings (Pydantic)
│   ├── errors.py         # Custom exception types
│   ├── exporter.py       # PDF & TXT export engine (fpdf2)
│   ├── main.py           # FastAPI app factory, static file serving
│   ├── mcp_client.py     # MCP subprocess runner client
│   ├── mcp_runner.py     # MCP subprocess entry point
│   ├── prompts.py        # All AI prompt templates (single source of truth)
│   ├── routes.py         # API route handlers (/research, /export, /health)
│   └── utils.py          # Logger setup
├── frontend/
│   ├── index.html        # App shell, MathJax integration
│   ├── style.css         # Dark glassmorphism UI design system
│   └── app.js            # SSE streaming client, markdown renderer, export
├── mcp_servers/
│   ├── __init__.py
│   ├── web_search_server.py    # MCP web search tool (DuckDuckGo)
│   └── filesystem_server.py    # MCP filesystem tool
├── outputs/              # Runtime PDF/TXT output directory (gitignored)
├── .env.example          # Environment variable template
├── .gitignore
├── CLAUDE.md             # AI coding context (architectural rules)
├── README.md
└── requirements.txt
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

Edit `.env` with your API keys:

```env
OPENROUTER_API_KEY=your-openrouter-key-here
GROQ_API_KEY=your-groq-key-here
PRIMARY_MODEL=openai/gpt-4o-mini
FALLBACK_MODEL=llama-3.3-70b-versatile
OUTPUT_DIR=outputs
```

> **Get free API keys:**
> - OpenRouter: [openrouter.ai](https://openrouter.ai) (many free models available)
> - Groq: [console.groq.com](https://console.groq.com) (free tier, very fast)

### 5. Run the server

```bash
uvicorn backend.main:app --reload --port 8000
```

Open **http://localhost:8000** in your browser.

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves the frontend UI |
| `/research` | GET (SSE) | Streams research results for a topic |
| `/export` | POST | Exports content as `.pdf` or `.txt` |
| `/health` | GET | Server health check |

### Example: Research endpoint

```
GET /research?topic=quantum+computing
```

**Stream response** (SSE events):

```json
{"type": "status",  "message": "Searching the web..."}
{"type": "content", "text": "## Overview\nQuantum computers..."}
{"type": "done",    "sources": ["https://..."], "model": "llama-3.3-70b"}
```

### Example: Export endpoint

```json
POST /export
{
  "content": "## Overview\n...",
  "filename": "quantum_computing",
  "format": "pdf"
}
```

---

## Code Quality Standards

- **Type hints** on all functions and variables
- **Docstrings** on every function following Google style
- **Centralised config** via `backend/config.py` — no hardcoded credentials anywhere
- **Centralised error handling** via `backend/errors.py`
- **Prompt isolation** — all AI prompts live only in `backend/prompts.py`
- **Separation of concerns** — AI logic in `agent.py`, HTTP in `routes.py`
- **Structured logging** via Python `logging` module throughout

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes* | — | OpenRouter API key (primary model) |
| `GROQ_API_KEY` | Yes* | — | Groq API key (fallback model) |
| `PRIMARY_MODEL` | No | `openai/gpt-4o-mini` | Primary OpenRouter model ID |
| `FALLBACK_MODEL` | No | `llama-3.3-70b-versatile` | Groq fallback model |
| `OUTPUT_DIR` | No | `outputs` | Directory for exported files |
| `MAX_TOKENS` | No | `1500` | Max tokens per AI response |

> *At least one of `OPENROUTER_API_KEY` or `GROQ_API_KEY` must be set.

---

## Security

- `.env` is listed in `.gitignore` and never committed
- All secrets are accessed only through `backend/config.py` using Pydantic Settings
- No credentials are hardcoded anywhere in the codebase
- CORS is configured for localhost development only

---

## Author

**Ashutosh Singh**
GitHub: [@ashyou09](https://github.com/ashyou09)
