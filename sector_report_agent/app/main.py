"""
Sector Report Agent - FastAPI Application

A Databricks App that acts as a sub-agent for the Supervisor Agent.
It receives chat messages via /invocations, extracts HTML content and filename,
converts to Word (.docx), and returns the result as a streaming SSE response.
"""

import os
import re
import json
import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
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
    """
    # Try 1: Direct JSON parse
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "filename" in data and "html_content" in data:
            return data["filename"], data["html_content"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Try 2: Find JSON block in the text
    json_patterns = [
        r'```json\s*\n?(\{.*?\})\s*\n?```',
        r'```\s*\n?(\{.*?\})\s*\n?```',
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

    # Try 3: Find JSON object with our keys anywhere in the content
    # Use a greedy approach to find the largest JSON-like structure
    try:
        # Find the start of a JSON object containing filename
        idx = content.find('"filename"')
        if idx == -1:
            idx = content.find("'filename'")
        if idx > -1:
            # Walk back to find the opening brace
            brace_start = content.rfind('{', 0, idx)
            if brace_start > -1:
                # Walk forward to find the matching closing brace
                brace_count = 0
                for i in range(brace_start, len(content)):
                    if content[i] == '{':
                        brace_count += 1
                    elif content[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = content[brace_start:i+1]
                            data = json.loads(json_str)
                            if "filename" in data and "html_content" in data:
                                return data["filename"], data["html_content"]
                            break
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Try 4: Look for filename and HTML content separately
    filename_match = re.search(r'filename["\':\s]+([\w\-]+\.docx)', content)
    html_match = re.search(r'(<!DOCTYPE html>.*?</html>|<html[^>]*>.*?</html>)', content, re.DOTALL | re.IGNORECASE)

    if filename_match and html_match:
        return filename_match.group(1), html_match.group(1)

    if html_match:
        return "report.docx", html_match.group(1)

    return None, None


def _make_sse_chunk(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


def _make_done_chunk() -> str:
    """Format the SSE done signal."""
    return "data: [DONE]\n\n"


CAPABILITIES_RESPONSE = (
    "I am the Sector Report converter. I convert HTML reports (including Chart.js charts) "
    "to Word documents (.docx). Send me a JSON message with 'filename' (ending in .docx) "
    "and 'html_content' (the full HTML string) and I will convert and save it."
)


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

    Receives chat messages, extracts filename + html_content,
    performs conversion, and returns an SSE streaming response.
    """
    body = await request.json()
    logger.info(f"Received /invocations request body keys: {list(body.keys())}")

    stream = body.get("stream", False)

    # Extract the last message content from the conversation
    messages = body.get("input", [])
    if not messages:
        messages = body.get("messages", [])

    last_content = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("content"):
            last_content = msg["content"]
            break

    logger.info(f"Last message content (first 300 chars): {last_content[:300]}")

    # Try to extract parameters from the message
    filename, html_content = _extract_params_from_message(last_content)

    if filename and html_content:
        try:
            result = _do_conversion(filename, html_content)
            response_text = (
                f"Report converted and saved successfully. "
                f"File: {result['filename']}. "
                f"Path: {result['path']}. "
                f"Status: {result['status']}"
            )
        except HTTPException as e:
            response_text = f"Error converting report: {e.detail}"
        except Exception as e:
            response_text = f"Error converting report: {str(e)}"
    else:
        response_text = CAPABILITIES_RESPONSE
        logger.info("No filename/html_content found in message, returning capabilities")

    # Return response in the appropriate format
    if stream:
        # Return as Server-Sent Events stream (text/event-stream)
        def generate_sse():
            # Send the response as a single chunk in OpenAI-compatible format
            chunk = {
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": response_text,
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
            yield _make_sse_chunk(chunk)
            yield _make_done_chunk()

        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
    else:
        # Return as regular JSON
        return {
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text,
                    },
                    "finish_reason": "stop",
                }
            ]
        }
