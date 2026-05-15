# Sector Report Agent

A Databricks App that acts as a **sub-agent** for a Databricks Supervisor Agent.  
The Supervisor Agent generates HTML reports with Chart.js visualizations, sends them to this app via the `/invocations` endpoint, and the app extracts chart data, renders charts with matplotlib, converts everything to Word documents (.docx), and saves the files to a Unity Catalog Volume.

## Purpose

This application serves as a **sub-agent tool** in a Supervisor Agent workflow:

1. The Supervisor Agent orchestrates report generation (data retrieval via Genie Space, analysis, HTML assembly with Chart.js).
2. Once the HTML report is ready, the agent calls this app's `/invocations` endpoint with a JSON message containing the filename and HTML content.
3. The app parses Chart.js configurations from `<script>` blocks.
4. Charts are rendered server-side as PNG images using matplotlib.
5. Text and tables are converted via `htmldocx`, chart images are inserted via `python-docx`.
6. The final .docx is saved to a Unity Catalog Volume using the Databricks SDK.
7. The app returns an SSE stream with the result (see Known Limitations below).

## How Chart Rendering Works

The agent generates HTML with Chart.js `<script>` blocks. Since there's no browser in the app container, charts are re-rendered with matplotlib:

1. Regex extracts `new Chart(...)` calls from `<script>` tags
2. Parses: chart type, labels, data arrays, dataset labels, colors, title
3. Renders equivalent chart with matplotlib → PNG bytes
4. Replaces `<canvas>` elements with text placeholders in the HTML
5. Converts cleaned HTML (text + tables) to DOCX via `htmldocx`
6. Post-processes the DOCX: finds placeholder paragraphs and replaces them with chart images via `python-docx`'s `add_picture()`

Supported chart types: **bar**, **line**, **pie**, **doughnut** (with fallback to bar for unknown types).

If the HTML contains no `<script>` tags (static HTML), it converts directly without chart processing.

## Endpoints

### `GET /health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "sector-report-agent"
}
```

### `POST /invocations` (Primary — used by Supervisor Agent)

The main endpoint called by the Databricks Supervisor Agent framework. Receives chat messages in the standard agent-to-agent format, extracts the filename and HTML content, performs the conversion, and returns an Anthropic-style SSE stream.

**Request Body (from Supervisor Agent):**
```json
{
  "input": [
    {
      "role": "user",
      "content": "{\"filename\": \"automotive_sector_report.docx\", \"html_content\": \"<!DOCTYPE html>...\"}"
    }
  ],
  "context": {...},
  "stream": true
}
```

The app extracts the JSON from the last message's `content` field.

**Response:** Server-Sent Events (`text/event-stream`) in Anthropic message format:
```
event: message_start
data: {"type": "message_start", "message": {"id": "msg_...", "role": "assistant", ...}}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Report saved successfully. File: automotive_sector_report.docx. Path: /Volumes/agentbricks/volumes/agent_reports/automotive_sector_report.docx."}}

event: content_block_stop
data: {"type": "content_block_stop", "index": 0}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 25}}

event: message_stop
data: {"type": "message_stop"}
```

### `POST /convert-to-docx` (Direct testing)

Direct endpoint for testing without the Supervisor Agent framework.

**Request Body:**
```json
{
  "filename": "automotive_sector_report.docx",
  "html_content": "<!DOCTYPE html><html>...(full HTML with Chart.js)...</html>"
}
```

**Response (success - 200):**
```json
{
  "status": "success",
  "path": "/Volumes/agentbricks/volumes/agent_reports/automotive_sector_report.docx",
  "filename": "automotive_sector_report.docx"
}
```

## Where Files Are Saved

```
/Volumes/agentbricks/volumes/agent_reports/
```

Configurable via the `REPORT_VOLUME_PATH` environment variable.

## Known Limitations & Workarounds

### SSE Stream Parsing Issue

The Databricks Supervisor Agent currently cannot parse the SSE stream returned by this app (reports "Tool returned no content"), even though the conversion completes successfully. This is a known compatibility issue between FastAPI's `StreamingResponse` and the Databricks agent infrastructure's SSE parser.

**Workaround:** The Supervisor Agent's system instructions include a directive to assume success if the tool returns no content, and to construct the file path as `/Volumes/agentbricks/volumes/agent_reports/{filename}` from the filename it sent. The conversion is reliable — every invocation successfully saves the .docx file.

**Status:** The file is always saved correctly. The only issue is the response stream not being parsed by the agent framework.

### Other Limitations

- **Supported chart types**: bar, line, pie, doughnut (others fall back to bar)
- **Chart.js extraction**: Agent must use `new Chart(document.getElementById('id'), {...})` pattern with simple data arrays
- **No JavaScript callbacks/functions** in chart configs (they are not executed)
- **Color handling**: Supports rgba() and hex; color arrays per-bar use only the first color
- **No external images**: Only matplotlib-rendered charts are embedded
- **No CSS styling**: Stripped during conversion
- **No FUSE filesystem**: UC Volume writes use SDK `files.upload()`, not direct file I/O

## Deployment

**App Name:** `agent-sector-report`  
**URL:** `agent-sector-report-3863256616093854.14.azure.databricksapps.com`

### Permissions Required

The app's service principal (`fa36362a-e6d6-49ad-9401-86a16796ff54`) needs:
- `USE CATALOG` on `agentbricks`
- `USE SCHEMA` on `agentbricks.volumes`
- `READ VOLUME` + `WRITE VOLUME` on `agentbricks.volumes.agent_reports`

## Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Testing

```bash
# Health check
curl -X GET http://localhost:8000/health

# Direct conversion (bypasses agent framework)
curl -X POST http://localhost:8000/convert-to-docx \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "test_report.docx",
    "html_content": "<html><body><h1>Test</h1><p>Hello world</p></body></html>"
  }'

# Simulate Supervisor Agent call
curl -X POST http://localhost:8000/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "input": [{"role": "user", "content": "{\"filename\": \"test.docx\", \"html_content\": \"<html><body><h1>Test</h1></body></html>\"}"}],
    "stream": true
  }'
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REPORT_VOLUME_PATH` | `/Volumes/agentbricks/volumes/agent_reports` | Target UC Volume path for saved reports |

## Dependencies

| Library | Purpose |
|---------|---------|
| fastapi | HTTP API framework |
| python-docx | Word document creation and image embedding |
| htmldocx | HTML text/table to DOCX conversion |
| beautifulsoup4 | HTML parsing |
| matplotlib | Server-side chart rendering |
| numpy | Numerical arrays for chart data |
| databricks-sdk | UC Volume file upload via Files API |

## Project Structure

```
sector_report_agent/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app with /invocations and /convert-to-docx
│   └── tools/
│       ├── __init__.py
│       └── html_to_docx_converter.py  # Chart extraction, rendering, DOCX assembly
├── docs/
│   ├── architecture.md            # System architecture diagram
│   └── agent_tool_contract.md     # Supervisor Agent integration contract
├── app.yaml                       # Databricks Apps configuration
├── requirements.txt               # Python dependencies
├── start.sh                       # Startup script
└── README.md                      # This file
```
