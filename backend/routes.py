"""
HTTP route definitions — validates input, calls agent/exporter, returns response.
Routes: POST /research (SSE stream), POST /export, GET /health.
Business logic stays in agent.py and exporter.py.
"""

from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse

from backend.agent import get_model_chain, run_research_workflow
from backend.exporter import export_pdf, export_txt
from backend.utils import ExportRequest, ResearchRequest, logger

router = APIRouter()

_MEDIA_TYPES: dict[str, str] = {"txt": "text/plain; charset=utf-8", "pdf": "application/pdf"}


@router.get("/health")
async def health() -> dict[str, object]:
    """Liveness check. Also reports which models are configured (never the keys)."""
    return {"status": "ok", "models": [m.model for m in get_model_chain()]}


@router.post("/research")
async def research(request: ResearchRequest) -> StreamingResponse:
    """Accept a research topic and stream a cited AI summary as Server-Sent Events."""
    logger.info(f"Research request received for topic: {request.topic}")
    return StreamingResponse(
        run_research_workflow(request.topic),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/export")
async def export(request: ExportRequest) -> Response:
    """Export research content as a downloadable .txt or .pdf file."""
    logger.info(f"Export request: format={request.format}, filename={request.filename}")

    exporter = export_pdf if request.format == "pdf" else export_txt
    data: bytes = exporter(request.content, request.filename)
    download_name: str = f"{request.filename}.{request.format}"

    return Response(
        content=data,
        media_type=_MEDIA_TYPES[request.format],
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )
