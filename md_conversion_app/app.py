from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from datetime import datetime
from databricks.sdk import WorkspaceClient
import re
import json

app = FastAPI()

REPORT_VOLUME_PATH = "/Volumes/agentbricks/volumes/agent_reports"
PICTURE_VOLUME_PATH = "/Volumes/agentbricks/volumes/pictures"

APP_BASE_URL = (
    "https://agent-md-conversion-app-3863256616093854.14.azure.databricksapps.com"
)

w = WorkspaceClient()


class MarkdownRequest(BaseModel):
    filename: str = "agent_report"
    content: str


@app.get("/")
def root():
    return {
        "success": True,
        "status": "running",
        "message": "Markdown conversion app is running.",
        "report_volume_path": REPORT_VOLUME_PATH,
        "picture_volume_path": PICTURE_VOLUME_PATH,
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


def get_picture_metadata_payload():
    files = list(
        w.files.list_directory_contents(
            directory_path=PICTURE_VOLUME_PATH,
        )
    )

    metadata_files = [
        file_info
        for file_info in files
        if file_info.name.endswith(".json")
    ]

    metadata = []

    for file_info in metadata_files:
        downloaded = w.files.download(file_path=file_info.path)
        raw_content = downloaded.contents.read().decode("utf-8")
        item = json.loads(raw_content)

        image_filename = item.get("chart_filename")

        if image_filename:
            item["image_url"] = f"{APP_BASE_URL}/image/{image_filename}"
            item["markdown_reference"] = (
                f"![{item.get('chart_title', image_filename)}]"
                f"({APP_BASE_URL}/image/{image_filename})"
            )

        metadata.append(item)

    return {
        "success": True,
        "status": "success",
        "operation": "picture_metadata",
        "message": "Available picture metadata returned successfully.",
        "picture_volume_path": PICTURE_VOLUME_PATH,
        "metadata": metadata,
    }


@app.post("/save-markdown")
def save_markdown(request: MarkdownRequest):
    result = save_markdown_file(
        request.filename,
        request.content,
    )

    return {
        "success": True,
        "status": "success",
        "operation": "save_markdown",
        "message": "Markdown report was successfully saved to the Unity Catalog Volume.",
        "result": result,
    }


@app.post("/invocations")
async def invocations(request: Request):
    try:
        payload = await request.json()

    except Exception:
        raw_body = await request.body()

        payload = {
            "operation": "save_markdown",
            "filename": "raw_agent_payload",
            "content": raw_body.decode(
                "utf-8",
                errors="replace",
            ),
        }

    operation = payload.get("operation")

    # ---------------------------------------------------
    # GET PICTURE METADATA
    # ---------------------------------------------------

    if operation == "get_picture_metadata":

        try:
            response_payload = get_picture_metadata_payload()

        except Exception as e:

            response_payload = {
                "success": False,
                "status": "failed",
                "operation": "picture_metadata",
                "error_type": type(e).__name__,
                "error_message": str(e),
            }

        return sse_response(response_payload)

    # ---------------------------------------------------
    # SAVE MARKDOWN
    # ---------------------------------------------------

    filename = (
        payload.get("filename")
        or "agent_report"
    )

    content = (
        payload.get("content")
        or payload.get("markdown")
        or payload.get("report")
        or ""
    )

    try:

        result = save_markdown_file(
            filename,
            content,
        )

        response_payload = {
            "success": True,
            "status": "success",
            "operation": "save_markdown",
            "message": (
                "Markdown report successfully saved."
            ),
            "result": result,
        }

    except Exception as e:

        response_payload = {
            "success": False,
            "status": "failed",
            "operation": "save_markdown",
            "error_type": type(e).__name__,
            "error_message": str(e),
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


@app.get("/picture-metadata")
def picture_metadata():
    try:
        return get_picture_metadata_payload()

    except Exception as e:
        return {
            "success": False,
            "status": "failed",
            "operation": "picture_metadata",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "picture_volume_path": PICTURE_VOLUME_PATH,
        }


@app.get("/image/{filename}")
def get_image(filename: str):
    try:
        safe_filename = filename.split("/")[-1]
        image_path = f"{PICTURE_VOLUME_PATH}/{safe_filename}"

        downloaded = w.files.download(file_path=image_path)
        image_bytes = downloaded.contents.read()

        if safe_filename.lower().endswith(".png"):
            media_type = "image/png"
        elif safe_filename.lower().endswith(".jpg") or safe_filename.lower().endswith(".jpeg"):
            media_type = "image/jpeg"
        else:
            media_type = "application/octet-stream"

        return Response(
            content=image_bytes,
            media_type=media_type,
        )

    except Exception as e:
        return {
            "success": False,
            "status": "failed",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "filename": filename,
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


@app.get("/test-picture-metadata")
def test_picture_metadata():
    return picture_metadata()