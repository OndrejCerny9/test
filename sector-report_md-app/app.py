from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from datetime import datetime
import os
import re
import json

app = FastAPI()

# PoC only: temporary local app storage.
# Files may disappear after app restart/redeploy.
OUTPUT_DIR = "/tmp/agent_reports"


class MarkdownRequest(BaseModel):
    filename: str = "agent_report"
    content: str


@app.get("/")
def root():
    return {"status": "running"}


def save_markdown_file(filename: str, content: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    safe_filename = re.sub(r"[^a-zA-Z0-9_-]", "_", filename or "agent_report")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{OUTPUT_DIR}/{safe_filename}_{timestamp}.md"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "status": "success",
        "path": path,
        "storage_note": "PoC only: file is saved in temporary local app storage, not Unity Catalog Volume.",
        "message": f"Markdown report saved to {path}",
    }


@app.post("/save-markdown")
def save_markdown(request: MarkdownRequest):
    return save_markdown_file(request.filename, request.content)


@app.post("/invocations")
async def invocations(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raw_body = await request.body()
        payload = {
            "filename": "raw_agent_payload",
            "content": raw_body.decode("utf-8", errors="replace"),
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
            + json.dumps(payload, indent=2, ensure_ascii=False)
            + "\n```"
        )

    if not isinstance(content, str):
        content = json.dumps(content, indent=2, ensure_ascii=False)

    result = save_markdown_file(filename, content)

    async def event_stream():
        yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


@app.get("/files")
def list_files():
    if not os.path.exists(OUTPUT_DIR):
        return {"files": []}

    return {"files": os.listdir(OUTPUT_DIR)}


@app.get("/download/{filename}")
def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(file_path):
        return {"error": "File not found"}

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="text/markdown",
    )