# CLAUDE.md — AI Research Assistant

## What this project does
A web app that accepts a research topic, calls AI models to generate
a structured research summary, uses MCP servers to fetch real web data,
and allows the user to export the result as .txt or .pdf.

## Tech stack
- Frontend: HTML/CSS/JS (vanilla, no framework)
- Backend: Python + FastAPI
- AI: OpenRouter (gpt-oss-120b:free) primary, Groq (llama-3.3-70b) fallback
- MCP: custom Python MCP servers (web search + filesystem)
- PDF export: fpdf2
- Environment: python-dotenv, uvicorn, pydantic-settings

## Key files — read these before making changes
- @backend/agent.py — the AI orchestration and tool-use loop. All AI logic lives here.
- @backend/mcp_client.py — the MCP bridge. Do NOT hardcode tool schemas here.
- @backend/prompts.py — system prompts. Edit this to change how AI responds.
- @backend/routes.py — HTTP routes. Two routes: POST /research, POST /export
- @backend/exporter.py — PDF/TXT export with LaTeX-to-plaintext sanitization.
- @backend/config.py — centralized settings. Never use os.environ directly.
- @mcp_servers/web_search_server.py — the MCP server that handles web search.

## Architecture decisions (do not change without reason)
- MCP servers run as subprocesses connected via stdio (same machine setup)
- AI API is called from agent.py ONLY — no direct API calls from routes.py
- All environment variables are read from config.py — never use os.environ directly
- Export files are written to /outputs/ — never write elsewhere
- Frontend serves from the same FastAPI server via StaticFiles mount

## Coding conventions
- Use Python type hints on all function signatures
- Write docstrings on every function (one-line minimum)
- Handle all errors using the custom classes in errors.py
- Keep prompts.py as the single source of truth for all prompt text
- Use comments to explain WHY, not WHAT

## Run commands
- Install deps: pip install -r requirements.txt
- Start server: uvicorn backend.main:app --reload --port 8000
- Open app: http://localhost:8000
- API docs: http://localhost:8000/docs

## Environment variables (see .env.example)
- OPENROUTER_API_KEY — required, get from openrouter.ai
- GROQ_API_KEY — required fallback, get from console.groq.com
- PRIMARY_MODEL — default: openai/gpt-oss-120b:free
- FALLBACK_MODEL — default: llama-3.3-70b-versatile
- MAX_TOKENS — default: 2000
- OUTPUT_DIR — default: ./outputs

## AI guide references
For Claude API usage (tool loops, multi-turn, streaming):
  see @CLAUDE_WORKING_GUIDE.md

For MCP server/client patterns (tools, resources, prompts):
  see @CLAUDE_MCP_AND_CLAUDECODE_GUIDE.md

For full project structure, file-by-file instructions, and error handling:
  see @AI_RESEARCH_ASSISTANT_PROJECT_GUIDE.md
