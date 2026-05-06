from fastapi import FastAPI, Request
from pydantic import BaseModel
from datetime import datetime
import os
import re
import json

app = FastAPI()

OUTPUT_DIR = "/Volumes/agentbricks/test/agent_reports"


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
        "path": path
    }


@app.post("/save-markdown")
def save_markdown(request: MarkdownRequest):
    return save_markdown_file(request.filename, request.content)


@app.post("/invocations")
async def invocations(request: Request):
    payload = await request.json()

    # Agent Bricks may send different payload shapes.
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

    # If content is still not a string, serialize full payload for debugging.
    if content is None:
        content = "# Debug Payload\n\n```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```"

    if not isinstance(content, str):
        content = json.dumps(content, indent=2, ensure_ascii=False)

    return save_markdown_file(filename, content)