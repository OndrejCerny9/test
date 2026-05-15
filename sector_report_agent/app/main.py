"""
Sector Report Agent - FastAPI Application

A Databricks App that exposes an HTTP tool endpoint for a Supervisor Agent.
The agent generates HTML reports and this app saves them to a Unity Catalog Volume.
"""

import os
import re
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from app.tools.html_report_saver import save_html_report

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sector Report Agent",
    description="HTTP tool endpoint for saving HTML reports to Unity Catalog Volumes.",
    version="1.0.0",
)


# --- Request / Response Models ---


class SaveReportRequest(BaseModel):
    """Request body for the save-html-report endpoint."""

    filename: str
    html_content: str

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Validate that filename ends with .html."""
        if not v.endswith(".html"):
            raise ValueError("Filename must end with .html")
        return v


class SaveReportResponse(BaseModel):
    """Response body for the save-html-report endpoint."""

    status: str
    path: str
    filename: str


# --- Helper Functions ---


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.

    - Strips directory components (e.g. ../../etc/passwd.html -> passwd.html)
    - Removes any characters that are not alphanumeric, hyphens, underscores, or dots.
    - Ensures the result still ends with .html.
    """
    # Extract only the basename (remove any directory traversal)
    filename = os.path.basename(filename)

    # Remove any characters that are not safe
    filename = re.sub(r"[^a-zA-Z0-9_\-.]", "_", filename)

    # Ensure it still ends with .html after sanitization
    if not filename.endswith(".html"):
        filename = filename + ".html"

    # Prevent empty filenames
    if filename == ".html":
        filename = "unnamed_report.html"

    return filename


# --- Endpoints ---


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "sector-report-agent"}


@app.post("/save-html-report", response_model=SaveReportResponse)
def save_html_report_endpoint(request: SaveReportRequest):
    """
    Save an HTML report to the configured Unity Catalog Volume.

    Accepts a filename and HTML content, sanitizes the filename,
    and persists the file to the volume.
    """
    # Sanitize the filename to prevent path traversal
    safe_filename = sanitize_filename(request.filename)
    logger.info(f"Saving report: {safe_filename}")

    try:
        result = save_html_report(
            filename=safe_filename,
            html_content=request.html_content,
        )
        return SaveReportResponse(**result)
    except OSError as e:
        logger.error(f"Failed to save report: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
