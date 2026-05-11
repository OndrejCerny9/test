from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from datetime import datetime
import os
import re
import json

app = FastAPI()

# Persistent Unity Catalog Volume storage
# Catalog: agentbricks
# Schema: volumes
# Volume: agent_reports
OUTPUT_DIR = "/Volumes/agentbricks/volumes/agent_reports"


class MarkdownRequest(BaseModel):
    filename: str = "agent_report"
    content: str


@app.get("/")
def root():
    return {
        "status": "running",
        "storage": OUTPUT_DIR,
    }


def save_markdown_file(filename: str, content: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    safe_filename = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        filename or "agent_report",
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_filename = f"{safe_filename}_{timestamp}.md"

    path = os.path.join(
        OUTPUT_DIR,
        output_filename,
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "status": "success",
        "filename": output_filename,
        "path": path,
        "volume": "agentbricks.volumes.agent_reports",
        "download_endpoint": f"/download/{output_filename}",
        "message": f"Markdown report saved to {path}",
    }


@app.post("/save-markdown")
def save_markdown(request: MarkdownRequest):
    return save_markdown_file(
        request.filename,
        request.content,
    )


@app.post("/invocations")
async def invocations(request: Request):
    try:
        payload = await request.json()

    except Exception:
        raw_body = await request.body()

        payload = {
            "filename": "raw_agent_payload",
            "content": raw_body.decode(
                "utf-8",
                errors="replace",
            ),
        }

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

    if content is None:
        content = (
            "# Debug Payload\n\n```json\n"
            + json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            )
            + "\n```"
        )

    if not isinstance(content, str):
        content = json.dumps(
            content,
            indent=2,
            ensure_ascii=False,
        )

    result = save_markdown_file(
        filename,
        content,
    )

    async def event_stream():
        yield (
            f"data: "
            f"{json.dumps(result, ensure_ascii=False)}\n\n"
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


@app.get("/files")
def list_files():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = []

    for filename in sorted(os.listdir(OUTPUT_DIR)):
        files.append(
            {
                "filename": filename,
                "download_endpoint": f"/download/{filename}",
            }
        )

    return {
        "storage": OUTPUT_DIR,
        "files": files,
    }


@app.get("/download/{filename}")
def download_file(filename: str):
    safe_filename = os.path.basename(filename)

    file_path = os.path.join(
        OUTPUT_DIR,
        safe_filename,
    )

    if not os.path.exists(file_path):
        return {
            "error": "File not found",
            "requested_file": safe_filename,
            "available_files": (
                os.listdir(OUTPUT_DIR)
                if os.path.exists(OUTPUT_DIR)
                else []
            ),
        }

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="text/markdown",
    )