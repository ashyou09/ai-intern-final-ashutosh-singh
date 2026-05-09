# 🔬 AI Research Assistant

An AI-powered research assistant that generates structured, publication-ready research summaries with real-time web search, academic paper discovery, and professional PDF/TXT export — all wrapped in a premium dark-themed UI with cinematic background animations.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **AI-Powered Summaries** | Generates structured reports with Overview, Key Findings, Details, and Related Papers |
| **Real-Time Web Search** | DuckDuckGo integration via MCP server — free, no API key required |
| **Academic Paper Search** | Searches arXiv, PubMed, Semantic Scholar, and Google Scholar |
| **Export Options** | Download research as professionally styled `.pdf` or `.txt` files |
| **Premium UI** | Midnight-blue glassmorphism design with laser particle animations |
| **MathJax Rendering** | Complex mathematical equations render beautifully in the browser |
| **LaTeX-to-Text PDF** | Automatic LaTeX sanitization ensures clean math in exported PDFs |
| **Clickable Links** | Source URLs are rendered as clickable blue links in both UI and PDF |
| **Cinematic Background** | Canvas-based laser beams with physics-driven collisions and global slow-motion |
| **MCP Integration** | Model Context Protocol servers for extensible tool use |
| **Error Handling** | Graceful handling of API failures, empty inputs, and edge cases |

---

## 🏗️ Architecture

```
ai-intern-final/
│
├── backend/                    # Python FastAPI backend
│   ├── __init__.py             # Package marker
│   ├── main.py                 # FastAPI entry point, CORS, error handlers
│   ├── config.py               # Centralized config via pydantic-settings
│   ├── routes.py               # HTTP routes: POST /research, POST /export
│   ├── agent.py                # AI orchestration — tool-use loop with streaming
│   ├── mcp_client.py           # MCP client bridge (subprocess + async)
│   ├── mcp_runner.py           # Standalone MCP tool runner (subprocess isolation)
│   ├── prompts.py              # System prompts (single source of truth)
│   ├── errors.py               # Custom exception classes + FastAPI handlers
│   ├── exporter.py             # PDF/TXT export with LaTeX sanitization
│   └── utils.py                # Pydantic models, validators, logging
│
├── mcp_servers/                # Model Context Protocol tool servers
│   ├── __init__.py             # Server registry with metadata
│   ├── web_search_server.py    # MCP server: DuckDuckGo web search
│   └── filesystem_server.py    # MCP server: save/read research files
│
├── frontend/                   # Vanilla HTML/CSS/JS frontend
│   ├── index.html              # Semantic HTML with all UI states + MathJax
│   ├── style.css               # Dark glassmorphism design system
│   └── app.js                  # API calls, markdown rendering, laser animation
│
├── outputs/                    # Generated PDF/TXT exports (git-ignored)
│   └── .gitkeep
│
├── CLAUDE.md                   # AI context: architecture, conventions, key files
├── CLAUDE_WORKING_GUIDE.md     # Claude API patterns (course modules 1 & 2)
├── CLAUDE_MCP_AND_CLAUDECODE_GUIDE.md  # MCP patterns (course modules 3 & 4)
├── AI_RESEARCH_ASSISTANT_PROJECT_GUIDE.md  # Full project structure & file instructions
├── .env                        # Actual secrets — NEVER commit this
├── .env.example                # Environment variable template
├── .gitignore                  # Git ignore rules
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

---

## 🚀 Quick Start

### 1. Clone & Set Up Environment

```bash
git clone <repo-url>
cd ai-intern-final
python -m venv venv
source venv/bin/activate        # macOS/Linux
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example .env
```

Edit `.env` and add your API keys:

```env
OPENROUTER_API_KEY=sk-or-v1-...     # Get free key at https://openrouter.ai
GROQ_API_KEY=gsk_...                 # Get free key at https://console.groq.com
```

> **Note:** Web search uses DuckDuckGo — completely free, no API key needed.

### 3. Start the Application

```bash
uvicorn backend.main:app --reload --port 8000
```

The server starts at `http://localhost:8000` and serves both the API and the frontend.

### 4. Use the App

1. Open `http://localhost:8000` in your browser
2. Enter a research topic in the search box
3. Click **Research** — the AI streams results in real-time
4. View the structured summary with rendered math and clickable sources
5. Click **Export .pdf** or **Export .txt** to download

---

## 📡 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/research` | Submit a topic, receive a streamed AI research summary |
| `POST` | `/export` | Export content as `.txt` or `.pdf` file download |
| `GET` | `/docs` | Interactive Swagger UI API documentation |

### POST /research

```json
{ "topic": "master theorem in DSA" }
```

Response: Server-Sent Events (SSE) stream with `type: "chunk"`, `"sources"`, and `"done"` events.

### POST /export

```json
{
  "content": "## Overview\nThe master theorem...",
  "filename": "master_theorem",
  "format": "pdf"
}
```

Response: File download (`.pdf` or `.txt`).

---

## 🔌 MCP Servers

The project uses the **Model Context Protocol** for extensible tool integration:

### Web Search Server (`mcp_servers/web_search_server.py`)
- **Tool:** `web_search` — Searches the web using DuckDuckGo
- **Protocol:** stdio (subprocess)
- **No API key required**

### Filesystem Server (`mcp_servers/filesystem_server.py`)
- **Tool:** `save_research` — Saves research summaries to JSON files
- **Resource:** `research://saved` — Lists all saved research files
- **Protocol:** stdio (subprocess)

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, Uvicorn |
| **AI Models** | OpenRouter (primary) + Groq (fallback) |
| **Web Search** | DuckDuckGo (free, no API key) |
| **MCP** | Model Context Protocol SDK |
| **PDF Export** | fpdf2 with LaTeX-to-plaintext sanitization |
| **Frontend** | Vanilla HTML/CSS/JS (no framework) |
| **Math Rendering** | MathJax 3 (CDN) |
| **Config** | pydantic-settings with `.env` |

---

## 📝 Coding Conventions

These conventions are enforced across the codebase (see `CLAUDE.md`):

- **Type hints** on all Python function signatures
- **Docstrings** on every function (one-line minimum)
- **Custom error classes** in `errors.py` — never expose raw stack traces
- **Single source of truth** — prompts live in `prompts.py`, config in `config.py`
- **Comments explain WHY**, not what the code does
- **No direct `os.environ`** — all env vars flow through `config.py`
- **Export files** always write to `outputs/` directory

---

## 📚 Architecture Guides

For full project details, these guides are the source of truth:

- **`AI_RESEARCH_ASSISTANT_PROJECT_GUIDE.md`** — Full project structure, file-by-file instructions, error handling checklist
- **`CLAUDE_WORKING_GUIDE.md`** — Claude API patterns: tool loops, multi-turn, streaming
- **`CLAUDE_MCP_AND_CLAUDECODE_GUIDE.md`** — MCP patterns: tools, resources, prompts, testing

---

## 📄 License

This project was built as part of an AI internship assignment. All rights reserved.
