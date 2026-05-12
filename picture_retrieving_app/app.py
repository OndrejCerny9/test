from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response
from databricks.sdk import WorkspaceClient
import json

app = FastAPI()

PICTURE_VOLUME_PATH = "/Volumes/agentbricks/volumes/pictures"

APP_BASE_URL = (
    "https://agent-picture-retrieving-app-3863256616093854.14.azure.databricksapps.com"
)

w = WorkspaceClient()


@app.get("/")
def root():
    return {
        "success": True,
        "status": "running",
        "message": "Image discovery app is running.",
        "picture_volume_path": PICTURE_VOLUME_PATH,
        "supported_operations": ["get_picture_metadata"],
    }


def sse_response(payload: dict):
    async def event_stream():
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


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

    readable_text_parts = []

    for item in metadata:
        readable_text_parts.append(
            "\n".join(
                [
                    f"Chart title: {item.get('chart_title', '')}",
                    f"Description: {item.get('description', '')}",
                    f"Suggested commentary: {item.get('suggested_commentary', '')}",
                    f"Markdown reference: {item.get('markdown_reference', '')}",
                ]
            )
        )

    readable_text = "\n\n---\n\n".join(readable_text_parts)

    if not readable_text:
        readable_text = "No chart metadata files were found."

    return {
        "success": True,
        "status": "success",
        "operation": "get_picture_metadata",
        "message": "Available picture metadata returned successfully.",
        "picture_volume_path": PICTURE_VOLUME_PATH,
        "metadata_count": len(metadata),
        "metadata": metadata,
        "content": readable_text,
        "text": readable_text,
        "instructions_for_agent": (
            "Use markdown_reference exactly as returned when inserting charts "
            "into markdown reports. Use description and suggested_commentary "
            "to write chart commentary."
        ),
    }


@app.get("/picture-metadata")
def picture_metadata():
    try:
        return get_picture_metadata_payload()

    except Exception as e:
        return {
            "success": False,
            "status": "failed",
            "operation": "get_picture_metadata",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "picture_volume_path": PICTURE_VOLUME_PATH,
        }


@app.post("/invocations")
async def invocations(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    try:
        response_payload = get_picture_metadata_payload()

    except Exception as e:
        response_payload = {
            "success": False,
            "status": "failed",
            "operation": "get_picture_metadata",
            "error_type": type(e).__name__,
            "error_message": str(e),
            "picture_volume_path": PICTURE_VOLUME_PATH,
            "content": f"Failed to retrieve picture metadata: {str(e)}",
            "text": f"Failed to retrieve picture metadata: {str(e)}",
        }

    return sse_response(response_payload)


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


@app.get("/test-picture-metadata")
def test_picture_metadata():
    return picture_metadata()