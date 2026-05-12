from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime
from databricks.sdk import WorkspaceClient
import re
import json

app = FastAPI()

REPORT_VOLUME_PATH = "/Volumes/agentbricks/volumes/agent_reports"

w = WorkspaceClient()


class MarkdownRequest(BaseModel):
    filename: str = "agent_report"
    content: str


@app.get("/")
def root():
    return {
        "success": True,
        "status": "running",
        "message": "Markdown saving app is running.",
        "report_volume_path": REPORT_VOLUME_PATH,
        "supported_operations": ["save_markdown"],
    }


def sse_response(payload: dict):
    async def event_stream():
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


def sanitize_filename(filename: str) -> str:
    return re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        filename or "agent_report",
    )


def save_markdown_file(filename: str, content: str):
    safe_filename = sanitize_filename(filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"{safe_filename}_{timestamp}.md"
    path = f"{REPORT_VOLUME_PATH}/{output_filename}"

    w.files.upload(
        file_path=path,
        contents=content.encode("utf-8"),
        overwrite=True,
    )

    return {
        "success": True,
        "status": "success",
        "filename": output_filename,
        "path": path,
        "volume": "agentbricks.volumes.agent_reports",
        "message": f"Markdown report successfully saved to {path}",
    }


def try_parse_json(value):
    if not isinstance(value, str):
        return value

    stripped = value.strip()

    if not (
        stripped.startswith("{")
        or stripped.startswith("[")
    ):
        return value

    try:
        return json.loads(stripped)
    except Exception:
        return value


def clean_markdown_content(content: str):
    if not isinstance(content, str):
        return None, content

    content = content.strip()

    parsed = try_parse_json(content)
    if parsed is not content:
        return extract_markdown_payload(parsed)

    patterns_with_filename = [
        'Save the following markdown report as "',
        'Save this markdown report with filename "',
    ]

    for pattern in patterns_with_filename:
        if content.startswith(pattern):
            try:
                filename = content.split(pattern, 1)[1].split('"', 1)[0]
                markdown_content = content.split(":\n\n", 1)[1]
                return filename, markdown_content
            except Exception:
                return None, content

    patterns_without_filename = [
        "Save this automotive industry analysis report:",
        "Save this markdown report:",
        "Save the following markdown report:",
        "Save this report:",
    ]

    for pattern in patterns_without_filename:
        if content.startswith(pattern):
            markdown_content = content.replace(pattern, "", 1).strip()
            return None, markdown_content

    return None, content


def extract_markdown_payload(payload):
    payload = try_parse_json(payload)

    if isinstance(payload, list) and len(payload) > 0:
        first_item = payload[0]

        if isinstance(first_item, dict):
            filename = (
                first_item.get("filename")
                or first_item.get("name")
                or first_item.get("report_name")
                or "agent_report"
            )

            content = (
                first_item.get("content")
                or first_item.get("markdown")
                or first_item.get("report")
                or first_item.get("text")
                or first_item.get("input")
            )

            extracted_filename, cleaned_content = clean_markdown_content(content)

            return (
                extracted_filename or filename,
                cleaned_content,
            )

    if isinstance(payload, dict):
        filename = (
            payload.get("filename")
            or payload.get("name")
            or payload.get("report_name")
            or "agent_report"
        )

        content = (
            payload.get("content")
            or payload.get("markdown")
            or payload.get("report")
            or payload.get("text")
            or payload.get("input")
        )

        extracted_filename, cleaned_content = clean_markdown_content(content)

        return (
            extracted_filename or filename,
            cleaned_content,
        )

    if isinstance(payload, str):
        extracted_filename, cleaned_content = clean_markdown_content(payload)
        return extracted_filename or "agent_report", cleaned_content

    return "agent_report", str(payload)


@app.post("/save-markdown")
def save_markdown(request: MarkdownRequest):
    filename, cleaned_content = extract_markdown_payload(
        {
            "filename": request.filename,
            "content": request.content,
        }
    )

    if not isinstance(cleaned_content, str):
        cleaned_content = json.dumps(
            cleaned_content,
            indent=2,
            ensure_ascii=False,
        )

    result = save_markdown_file(
        filename,
        cleaned_content,
    )

    return {
        "success": True,
        "status": "success",
        "operation": "save_markdown",
        "message": "Markdown report was successfully saved to the Unity Catalog Volume.",
        "result": result,
        "content": f"Markdown report saved successfully to {result['path']}",
        "text": f"Markdown report saved successfully to {result['path']}",
    }


@app.post("/invocations")
async def invocations(request: Request):
    raw_body = await request.body()
    raw_text = raw_body.decode("utf-8", errors="replace")

    try:
        payload = json.loads(raw_text)
    except Exception:
        payload = raw_text

    filename, content = extract_markdown_payload(payload)

    if content is None:
        content = (
            "# Debug Payload\n\n```json\n"
            + json.dumps(payload, indent=2, ensure_ascii=False)
            + "\n```"
        )

    if not isinstance(content, str):
        content = json.dumps(
            content,
            indent=2,
            ensure_ascii=False,
        )

    try:
        result = save_markdown_file(filename, content)

        response_payload = {
            "success": True,
            "status": "success",
            "operation": "save_markdown",
            "message": "Markdown report was successfully saved to the Unity Catalog Volume.",
            "result": result,
            "content": f"Markdown report saved successfully to {result['path']}",
            "text": f"Markdown report saved successfully to {result['path']}",
        }

    except Exception as e:
        response_payload = {
            "success": False,
            "status": "failed",
            "operation": "save_markdown",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "report_volume_path": REPORT_VOLUME_PATH,
            "content": f"Failed to save markdown report: {str(e)}",
            "text": f"Failed to save markdown report: {str(e)}",
        }

    return sse_response(response_payload)


@app.get("/files")
def list_files():
    try:
        files = list(
            w.files.list_directory_contents(
                directory_path=REPORT_VOLUME_PATH,
            )
        )

        return {
            "success": True,
            "status": "success",
            "report_volume_path": REPORT_VOLUME_PATH,
            "files": [
                {
                    "path": file_info.path,
                    "name": file_info.name,
                }
                for file_info in files
            ],
        }

    except Exception as e:
        return {
            "success": False,
            "status": "failed",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "report_volume_path": REPORT_VOLUME_PATH,
        }


@app.get("/test-volume-write")
def test_volume_write():
    try:
        test_content = (
            "# Volume Write Test\n\n"
            "This file was created by the Markdown Saving App."
        )

        result = save_markdown_file(
            filename="test_volume_write",
            content=test_content,
        )

        return {
            "success": True,
            "status": "success",
            "message": "Volume write test completed successfully.",
            "result": result,
        }

    except Exception as e:
        return {
            "success": False,
            "status": "failed",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "report_volume_path": REPORT_VOLUME_PATH,
        }