"""
Sector Report Agent - FastAPI Application

A Databricks App that exposes an HTTP tool endpoint for a Supervisor Agent.
The agent generates HTML reports (including Chart.js visualizations) and this app
parses chart configs, renders them with matplotlib, converts to Word (.docx),
and saves to a Unity Catalog Volume.
"""

import os
import re
import logging
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.tools.html_to_docx_converter import convert_html_to_docx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sector Report Agent",
    description="HTTP tool endpoint that converts HTML reports (with Chart.js) to Word (.docx) documents.",
    version="2.0.0",
)


# --- Request / Response Models ---


class ConvertReportRequest(BaseModel):
    """Request body for the convert-to-docx endpoint."""

    filename: str
    html_content: str

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate that filename ends with .docx."""
        if not v.endswith(".docx"):
            raise ValueError("Filename must end with .docx")
        return v


class ConvertReportResponse(BaseModel):
    """Response body for the convert-to-docx endpoint."""

    status: str
    path: str
    filename: str


# --- Helper Functions ---


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.
    """
    filename = os.path.basename(filename)
    filename = re.sub(r"[^a-zA-Z0-9_\-.]", "_", filename)
    if not filename.endswith(".docx"):
        filename = filename + ".docx"
    if filename == ".docx":
        filename = "unnamed_report.docx"
    return filename


def _do_conversion(filename: str, html_content: str) -> dict:
    """Shared conversion logic for both endpoints."""
    safe_filename = sanitize_filename(filename)
    logger.info(f"Converting and saving report: {safe_filename}")

    try:
        result = convert_html_to_docx(
            filename=safe_filename,
            html_content=html_content,
        )
        return result
    except ValueError as e:
        logger.error(f"Conversion error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except OSError as e:
        logger.error(f"Failed to save report: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# --- Endpoints ---


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "sector-report-agent"}


@app.post("/convert-to-docx", response_model=ConvertReportResponse)
def convert_to_docx_endpoint(request: ConvertReportRequest):
    """
    Convert an HTML report to a Word document (.docx) and save it.
    """
    result = _do_conversion(request.filename, request.html_content)
    return ConvertReportResponse(**result)


@app.post("/invocations")
async def invocations_endpoint(request: Request):
    """
    Endpoint called by the Databricks Supervisor Agent app tool.
    Accepts the same payload as /convert-to-docx.
    """
    body = await request.json()
    logger.info(f"Received /invocations call: {list(body.keys())}")

    # Extract filename and html_content from the request body
    filename = body.get("filename")
    html_content = body.get("html_content")

    if not filename or not html_content:
        raise HTTPException(
            status_code=400,
            detail="Request must include 'filename' (ending in .docx) and 'html_content' fields."
        )

    if not filename.endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="Filename must end with .docx"
        )

    result = _do_conversion(filename, html_content)
    return result
