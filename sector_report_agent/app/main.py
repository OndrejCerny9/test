"""
Sector Report Agent - FastAPI Application

A Databricks App that exposes an HTTP tool endpoint for a Supervisor Agent.
The agent generates HTML reports (including Chart.js visualizations) and this app
renders them with a headless browser, converts them to Word documents (.docx),
and saves them to a Unity Catalog Volume.
"""

import os
import re
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from app.tools.html_to_docx_converter import convert_html_to_docx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sector Report Agent",
    description="HTTP tool endpoint that renders HTML reports (including JS charts) and converts them to Word (.docx) documents.",
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

    - Strips directory components (e.g. ../../etc/passwd.docx -> passwd.docx)
    - Removes any characters that are not alphanumeric, hyphens, underscores, or dots.
    - Ensures the result still ends with .docx.
    """
    # Extract only the basename (remove any directory traversal)
    filename = os.path.basename(filename)

    # Remove any characters that are not safe
    filename = re.sub(r"[^a-zA-Z0-9_\-.]", "_", filename)

    # Ensure it still ends with .docx after sanitization
    if not filename.endswith(".docx"):
        filename = filename + ".docx"

    # Prevent empty filenames
    if filename == ".docx":
        filename = "unnamed_report.docx"

    return filename


# --- Endpoints ---


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "sector-report-agent"}


@app.post("/convert-to-docx", response_model=ConvertReportResponse)
def convert_to_docx_endpoint(request: ConvertReportRequest):
    """
    Convert an HTML report to a Word document (.docx) and save it to the
    configured Unity Catalog Volume.

    Supports HTML with JavaScript-rendered charts (Chart.js, etc.).
    The HTML is rendered in a headless browser before conversion.
    """
    # Sanitize the filename to prevent path traversal
    safe_filename = sanitize_filename(request.filename)
    logger.info(f"Converting and saving report: {safe_filename}")

    try:
        result = convert_html_to_docx(
            filename=safe_filename,
            html_content=request.html_content,
        )
        return ConvertReportResponse(**result)
    except ValueError as e:
        logger.error(f"Conversion error: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except OSError as e:
        logger.error(f"Failed to save report: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
