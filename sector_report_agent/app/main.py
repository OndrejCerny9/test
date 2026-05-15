"""
Sector Report Agent - FastAPI Application

A Databricks App that acts as a sub-agent for the Supervisor Agent.
It receives chat messages via /invocations, extracts HTML content and filename,
converts to Word (.docx), and returns the result as a chat response.
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
    description="Sub-agent that converts HTML reports (with Chart.js) to Word (.docx) documents.",
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
    """Shared conversion logic."""
    safe_filename = sanitize_filename(filename)
    logger.info(f"Converting and saving report: {safe_filename}")
    result = convert_html_to_docx(
        filename=safe_filename,
        html_content=html_content,
    )
    return result


def _extract_params_from_message(content: str) -> tuple:
    """
    Try to extract filename and html_content from a message.
    
    Supports:
    - Pure JSON: {"filename": "...", "html_content": "..."}
    - JSON embedded in text (between ```json ... ``` or just {...})
    - Structured text with clear filename and HTML sections
    """
    # Try 1: Direct JSON parse
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "filename" in data and "html_content" in data:
            return data["filename"], data["html_content"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Try 2: Find JSON block in the text (```json ... ``` or naked JSON)
    json_patterns = [
        r'```json\s*\n?(\{.*?\})\s*\n?```',  # ```json {...} ```
        r'```\s*\n?(\{.*?\})\s*\n?```',       # ``` {...} ```
        r'(\{[^{}]*"filename"[^{}]*"html_content"[^{}]*\})',  # inline JSON with our keys
    ]
    for pattern in json_patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "filename" in data and "html_content" in data:
                    return data["filename"], data["html_content"]
            except (json.JSONDecodeError, TypeError):
                continue

    # Try 3: Look for filename and HTML content separately in the text
    filename_match = re.search(r'filename["\':\s]+([\w\-]+\.docx)', content)
    
    # Look for HTML content (starts with <!DOCTYPE or <html)
    html_match = re.search(r'(<!DOCTYPE html>.*?</html>|<html[^>]*>.*?</html>)', content, re.DOTALL | re.IGNORECASE)
    
    if filename_match and html_match:
        return filename_match.group(1), html_match.group(1)

    # Try 4: If there's HTML content but no explicit filename, generate one
    if html_match:
        return "report.docx", html_match.group(1)

    return None, None


CAPABILITIES_RESPONSE = """I am the Sector Report converter. I convert HTML reports (including Chart.js charts) to Word documents (.docx).

To use me, send a message containing:
1. A filename ending in .docx (e.g., "automotive_sector_report.docx")
2. The full HTML content of the report

You can send these as JSON:
{"filename": "report.docx", "html_content": "<!DOCTYPE html><html>...</html>"}

Or include them naturally in your message - I will extract the HTML and filename automatically.

I support: headings, paragraphs, tables, lists, bold/italic text, and Chart.js charts (bar, line, pie, doughnut)."""


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
    Sub-agent endpoint called by the Databricks Supervisor Agent.
    
    Receives chat messages in format:
    {"input": [{"role": "user", "content": "..."}], "context": {...}, "stream": bool}
    
    Extracts filename + html_content from the message content,
    performs conversion, and returns a chat-style response.
    """
    body = await request.json()
    logger.info(f"Received /invocations request body keys: {list(body.keys())}")

    # Extract the last message content from the conversation
    messages = body.get("input", [])
    if not messages:
        messages = body.get("messages", [])

    last_content = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("content"):
            last_content = msg["content"]
            break

    logger.info(f"Last message content (first 500 chars): {last_content[:500]}")

    # Try to extract parameters from the message
    filename, html_content = _extract_params_from_message(last_content)

    if filename and html_content:
        # Perform conversion
        try:
            result = _do_conversion(filename, html_content)
            response_text = (
                f"Report converted and saved successfully.\n"
                f"- **File**: {result['filename']}\n"
                f"- **Path**: {result['path']}\n"
                f"- **Status**: {result['status']}"
            )
        except HTTPException as e:
            response_text = f"Error converting report: {e.detail}"
        except Exception as e:
            response_text = f"Error converting report: {str(e)}"
    else:
        # No valid parameters found - return capabilities description
        response_text = CAPABILITIES_RESPONSE
        logger.info("No filename/html_content found in message, returning capabilities")

    # Return in the agent response format
    return {
        "output": response_text
    }
