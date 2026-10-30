"""
HTTP route definitions — validates input, calls agent/exporter, returns response.
Routes: POST /research (SSE stream), POST /export, GET /providers, GET /health.
Business logic stays in agent.py and exporter.py.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse

from backend.agent import get_model_chain, run_research_workflow
from backend.exporter import export_md, export_pdf, export_txt
from backend.providers import PROVIDERS
from backend.ratelimit import research_rate_limit
from backend.utils import ExportRequest, ResearchRequest, logger

router = APIRouter()

_EXPORTERS = {
    "txt": (export_txt, "text/plain; charset=utf-8"),
    "md": (export_md, "text/markdown; charset=utf-8"),
    "pdf": (export_pdf, "application/pdf"),
}


@router.get("/health")
async def health() -> dict[str, object]:
    """Liveness check. Also reports which models are configured (never the keys)."""
    return {"status": "ok", "models": [m.model for m in get_model_chain()]}


@router.get("/providers")
async def providers() -> list[dict[str, str]]:
    """Providers a visitor can choose for "bring your own key"."""
    return [
        {"id": p.id, "name": p.name, "default_model": p.default_model, "key_url": p.key_url}
        for p in PROVIDERS.values()
    ]


@router.post("/research", dependencies=[Depends(research_rate_limit)])
async def research(request: ResearchRequest) -> StreamingResponse:
    """Accept a research topic and stream a cited AI summary as Server-Sent Events."""
    logger.info(f"Research request received for topic: {request.topic}")
    return StreamingResponse(
        run_research_workflow(request.topic, request.llm),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/export")
async def export(request: ExportRequest) -> Response:
    """Export research content as a downloadable .txt, .md or .pdf file."""
    logger.info(f"Export request: format={request.format}, filename={request.filename}")

    exporter, media_type = _EXPORTERS[request.format]
    data: bytes = exporter(request.content, request.filename)
    download_name: str = f"{request.filename}.{request.format}"

    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
