# Sector Report Agent

A Databricks App that exposes an HTTP tool endpoint for a Databricks Supervisor Agent.  
The Supervisor Agent generates HTML reports with Chart.js visualizations, and this app extracts chart data, renders charts with matplotlib, converts everything to Word documents (.docx), and saves the files to a Unity Catalog Volume.

## Purpose

This application serves as a **tool endpoint** for a Supervisor Agent workflow:

1. The Supervisor Agent orchestrates report generation (data retrieval, analysis, HTML assembly with Chart.js).
2. Once the HTML report is ready, the agent calls this app's `/convert-to-docx` endpoint.
3. The app parses Chart.js configurations from `<script>` blocks.
4. Charts are rendered server-side as PNG images using matplotlib.
5. Text and tables are converted via `htmldocx`, chart images are inserted via `python-docx`.
6. The final .docx is saved to a Unity Catalog Volume using the Databricks SDK.

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

### `POST /convert-to-docx`

Converts HTML (including Chart.js) to a Word document (.docx) and saves it.

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

**Response (conversion error - 422):**
```json
{
  "detail": "HTML to DOCX conversion failed: [error details]"
}
```

**Response (save error - 500):**
```json
{
  "detail": "Failed to write report to /Volumes/..."
}
```

## Where Files Are Saved

```
/Volumes/agentbricks/volumes/agent_reports/
```

Configurable via the `REPORT_VOLUME_PATH` environment variable.

## Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Testing

```bash
curl -X GET http://localhost:8000/health

curl -X POST http://localhost:8000/convert-to-docx \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "test_report.docx",
    "html_content": "<html><body><h1>Test</h1><p>Hello world</p></body></html>"
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

## Permissions

The app's service principal needs:
- `USE CATALOG` on the target catalog
- `USE SCHEMA` on the target schema
- `READ VOLUME` + `WRITE VOLUME` on the target volume
