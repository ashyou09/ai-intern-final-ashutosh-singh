"""
HTTP route definitions — validates input, calls agent, returns response.
Two routes: POST /research and POST /export.
Business logic stays in agent.py and exporter.py.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from backend.agent import run_research_workflow
from backend.exporter import export_txt, export_pdf
from backend.errors import (
    EmptyTopicError,
    TopicTooLongError,
    ClaudeAPIError,
    MCPConnectionError,
    ExportError,
)
from backend.utils import ResearchRequest, ExportRequest, ResearchResponse, logger

router = APIRouter()


@router.post("/research")
async def research(request: ResearchRequest):
    """
    Accept a research topic and stream a structured AI-generated summary using SSE.
    """
    topic: str = request.topic
    logger.info(f"Research request received for topic: {topic}")

    try:
        return StreamingResponse(
            run_research_workflow(topic),
            media_type="text/event-stream"
        )
    except Exception as e:
        logger.error(f"Unexpected error during research setup: {e}")
        raise HTTPException(status_code=500, detail="Research failed. Please try again.")


@router.post("/export")
async def export(request: ExportRequest) -> FileResponse:
    """
    Export research content as a downloadable .txt or .pdf file.
    Validates input, generates the file, and returns it as a download.
    """
    logger.info(f"Export request: format={request.format}, filename={request.filename}")

    try:
        file_path: str
        media_type: str

        if request.format == "txt":
            file_path = export_txt(request.content, request.filename)
            media_type = "text/plain"
        elif request.format == "pdf":
            file_path = export_pdf(request.content, request.filename)
            media_type = "application/pdf"
        else:
            raise HTTPException(status_code=400, detail="Format must be 'txt' or 'pdf'.")

        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=f"{request.filename}.{request.format}",
            headers={"Content-Disposition": f"attachment; filename={request.filename}.{request.format}"},
        )

    except ExportError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected export error: {e}")
        raise HTTPException(status_code=500, detail="Export failed. Please try again.")
