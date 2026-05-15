"""
Sector Report Agent - FastAPI Application

A Databricks App that exposes an HTTP tool endpoint for a Supervisor Agent.
The agent generates HTML reports (including Chart.js visualizations) and this app
parses chart configs, renders them with matplotlib, converts to Word (.docx),
and saves to a Unity Catalog Volume.
"""

import os
import re
import json
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
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
    """Sanitize filename to prevent path traversal attacks."""
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
    """Convert an HTML report to a Word document (.docx) and save it."""
    result = _do_conversion(request.filename, request.html_content)
    return ConvertReportResponse(**result)


@app.post("/invocations")
async def invocations_endpoint(request: Request):
    """
    Endpoint called by the Databricks Supervisor Agent app tool.

    The Supervisor Agent sends requests in various formats. This endpoint
    handles the common patterns and extracts filename + html_content.
    """
    body = await request.json()
    logger.info(f"Received /invocations request body keys: {list(body.keys())}")
    logger.info(f"Full /invocations request body: {json.dumps(body)[:2000]}")

    # --- Try to extract filename and html_content from different payload formats ---

    filename = None
    html_content = None

    # Format 1: Direct payload {"filename": "...", "html_content": "..."}
    if "filename" in body and "html_content" in body:
        filename = body["filename"]
        html_content = body["html_content"]

    # Format 2: Wrapped in "inputs" or "input" (common for serving endpoints)
    elif "inputs" in body:
        inputs = body["inputs"]
        if isinstance(inputs, dict):
            filename = inputs.get("filename")
            html_content = inputs.get("html_content")
        elif isinstance(inputs, list) and len(inputs) > 0:
            first = inputs[0]
            if isinstance(first, dict):
                filename = first.get("filename")
                html_content = first.get("html_content")

    elif "input" in body:
        inp = body["input"]
        if isinstance(inp, dict):
            filename = inp.get("filename")
            html_content = inp.get("html_content")

    # Format 3: OpenAI-style messages format
    elif "messages" in body:
        messages = body["messages"]
        # Look for the last tool_call or user message with our params
        for msg in reversed(messages):
            if isinstance(msg, dict):
                content = msg.get("content", "")
                if isinstance(content, str):
                    try:
                        parsed = json.loads(content)
                        if "filename" in parsed and "html_content" in parsed:
                            filename = parsed["filename"]
                            html_content = parsed["html_content"]
                            break
                    except (json.JSONDecodeError, TypeError):
                        pass

    # Format 4: Dataframe split format {"dataframe_split": {"columns": [...], "data": [...]}}
    elif "dataframe_split" in body:
        df = body["dataframe_split"]
        columns = df.get("columns", [])
        data = df.get("data", [])
        if data and len(data) > 0:
            row = dict(zip(columns, data[0]))
            filename = row.get("filename")
            html_content = row.get("html_content")

    if not filename or not html_content:
        logger.error(f"Could not extract filename/html_content from body. Keys: {list(body.keys())}")
        logger.error(f"Body preview: {json.dumps(body)[:1000]}")
        return JSONResponse(
            status_code=400,
            content={
                "error": "Could not extract 'filename' and 'html_content' from request.",
                "received_keys": list(body.keys()),
                "hint": "Send JSON with 'filename' (ending in .docx) and 'html_content' fields."
            }
        )

    if not filename.endswith(".docx"):
        filename = filename + ".docx"

    result = _do_conversion(filename, html_content)
    return result
