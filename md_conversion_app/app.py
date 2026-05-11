from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import datetime
from databricks.sdk import WorkspaceClient
import re
import json

app = FastAPI()

# Unity Catalog Volume
VOLUME_PATH = "/Volumes/agentbricks/volumes/agent_reports"

# Databricks Workspace client
w = WorkspaceClient()


class MarkdownRequest(BaseModel):
    filename: str = "agent_report"
    content: str


@app.get("/")
def root():
    return {
        "status": "running",
        "volume_path": VOLUME_PATH,
    }


def save_markdown_file(filename: str, content: str):
    safe_filename = re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        filename or "agent_report",
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output_filename = f"{safe_filename}_{timestamp}.md"

    path = f"{VOLUME_PATH}/{output_filename}"

    w.files.upload(
        file_path=path,
        contents=content.encode("utf-8"),
        overwrite=True,
    )

    return {
        "status": "success",
        "filename": output_filename,
        "path": path,
        "volume": "agentbricks.volumes.agent_reports",
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
    try:
        files = w.files.list_directory_contents(
            directory_path=VOLUME_PATH,
        )

        return {
            "status": "success",
            "volume_path": VOLUME_PATH,
            "files": [
                {
                    "path": f.path,
                    "name": f.name,
                }
                for f in files.contents
            ],
        }

    except Exception as e:
        return {
            "status": "failed",
            "error_type": type(e).__name__,
            "error_message": str(e),
        }


@app.get("/test-volume-write")
def test_volume_write():
    try:
        test_content = (
            "# Volume Write Test\n\n"
            "This file was created by the Databricks App."
        )

        result = save_markdown_file(
            filename="test_volume_write",
            content=test_content,
        )

        return {
            "test_status": "success",
            "result": result,
        }

    except Exception as e:
        return {
            "test_status": "failed",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "volume_path": VOLUME_PATH,
        }