"""
Sector Report Agent - FastAPI Application

Sub-agent for the Supervisor Agent. Receives chat messages,
extracts HTML + filename, converts to .docx, returns SSE stream.
"""

import os
import re
import json
import logging
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from app.tools.html_to_docx_converter import convert_html_to_docx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Sector Report Agent", version="2.0.0")


class ConvertReportRequest(BaseModel):
    filename: str
    html_content: str

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        if not v.endswith(".docx"):
            raise ValueError("Filename must end with .docx")
        return v


class ConvertReportResponse(BaseModel):
    status: str
    path: str
    filename: str


def sanitize_filename(filename: str) -> str:
    filename = os.path.basename(filename)
    filename = re.sub(r"[^a-zA-Z0-9_\-.]", "_", filename)
    if not filename.endswith(".docx"):
        filename = filename + ".docx"
    if filename == ".docx":
        filename = "unnamed_report.docx"
    return filename


def _do_conversion(filename: str, html_content: str) -> dict:
    safe_filename = sanitize_filename(filename)
    logger.info(f"Converting and saving report: {safe_filename}")
    return convert_html_to_docx(filename=safe_filename, html_content=html_content)


def _extract_params_from_message(content: str) -> tuple:
    """Extract filename and html_content from a message."""
    # Try direct JSON parse
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "filename" in data and "html_content" in data:
            return data["filename"], data["html_content"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Try finding JSON with brace matching
    try:
        idx = content.find('"filename"')
        if idx > -1:
            brace_start = content.rfind("{", 0, idx)
            if brace_start > -1:
                brace_count = 0
                for i in range(brace_start, len(content)):
                    if content[i] == "{":
                        brace_count += 1
                    elif content[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = content[brace_start:i+1]
                            data = json.loads(json_str)
                            if "filename" in data and "html_content" in data:
                                return data["filename"], data["html_content"]
                            break
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Try finding HTML directly
    html_pat = r"(<!DOCTYPE html>.*?</html>|<html[^>]*>.*?</html>)"
    html_match = re.search(html_pat, content, re.DOTALL | re.IGNORECASE)
    if html_match:
        fn_pat = r"[\w\-]+\.docx"
        fn_match = re.search(fn_pat, content)
        fn = fn_match.group(0) if fn_match else "report.docx"
        return fn, html_match.group(1)

    return None, None

def _sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event with proper newlines."""
    # Each SSE event: "event: <type>\ndata: <json>\n\n"
    line1 = "event: " + event_type
    line2 = "data: " + json.dumps(data)
    return line1 + "\n" + line2 + "\n\n"


CAPABILITIES = (
    "I convert HTML reports (with Chart.js) to Word (.docx). "
    "Send JSON with filename (ending .docx) and html_content."
)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "sector-report-agent"}


@app.post("/convert-to-docx", response_model=ConvertReportResponse)
def convert_to_docx_endpoint(request: ConvertReportRequest):
    result = _do_conversion(request.filename, request.html_content)
    return ConvertReportResponse(**result)


@app.post("/invocations")
async def invocations_endpoint(request: Request):
    """Sub-agent endpoint for Supervisor Agent."""
    body = await request.json()
    logger.info(f"Received /invocations keys: {list(body.keys())}")

    messages = body.get("input", []) or body.get("messages", [])
    last_content = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("content"):
            last_content = msg["content"]
            break

    logger.info(f"Message (first 200): {last_content[:200]}")
    filename, html_content = _extract_params_from_message(last_content)

    def generate():
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"

        # message_start - sent immediately to keep connection alive
        yield _sse_event("message_start", {
            "type": "message_start",
            "message": {"id": msg_id, "type": "message", "role": "assistant",
                        "content": [], "model": "sector-report-agent", "stop_reason": None}
        })

        # content_block_start
        yield _sse_event("content_block_start", {
            "type": "content_block_start", "index": 0,
            "content_block": {"type": "text", "text": ""}
        })

        # Do the conversion work
        if filename and html_content:
            try:
                result = _do_conversion(filename, html_content)
                text = f"Report saved successfully. File: {result['filename']}. Path: {result['path']}."
            except Exception as e:
                text = f"Error converting report: {str(e)}"
        else:
            text = CAPABILITIES

        # content_block_delta with actual text
        yield _sse_event("content_block_delta", {
            "type": "content_block_delta", "index": 0,
            "delta": {"type": "text_delta", "text": text}
        })

        # content_block_stop
        yield _sse_event("content_block_stop", {"type": "content_block_stop", "index": 0})

        # message_delta
        yield _sse_event("message_delta", {
            "type": "message_delta", "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": len(text.split())}
        })

        # message_stop
        yield _sse_event("message_stop", {"type": "message_stop"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
