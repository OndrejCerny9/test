from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import os
import re

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

    safe_filename = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)
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
def invocations(request: MarkdownRequest):
    return save_markdown_file(request.filename, request.content)