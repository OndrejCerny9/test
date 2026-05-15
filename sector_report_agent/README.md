# Sector Report Agent

A Databricks App that exposes an HTTP tool endpoint for a Databricks Supervisor Agent.  
The Supervisor Agent generates HTML reports (including Chart.js visualizations), and this app renders them in a headless browser, converts them to Word documents (.docx), and saves the resulting files into a Unity Catalog Volume.

## Purpose

This application serves as a **tool endpoint** for a Supervisor Agent workflow:

1. The Supervisor Agent orchestrates report generation (data retrieval, chart creation, HTML assembly with Chart.js).
2. Once the HTML report is ready, the agent calls this app's `/convert-to-docx` endpoint.
3. The app renders the HTML in headless Chromium (executing JavaScript to render charts).
4. Canvas-based charts are converted to inline PNG images.
5. The rendered HTML is converted to a Word document (.docx) and saved to a Unity Catalog Volume.

## How Chart Rendering Works

The agent generates HTML with `<script>` tags for Chart.js (or similar JS charting libraries). The app:

1. Detects `<script>` tags in the HTML
2. Loads the HTML in headless Chromium via Playwright
3. Waits for charts to render (JavaScript execution)
4. Converts each `<canvas>` element to a base64 PNG image
5. Replaces canvases with `<img>` tags in the DOM
6. Extracts the rendered HTML (now with static images instead of JS charts)
7. Converts the static HTML to DOCX using `htmldocx`

If the HTML has no scripts (pure static HTML), it skips Playwright and converts directly.

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

Renders HTML (including JS charts) and converts to a Word document (.docx).

**Request Body:**
```json
{
  "filename": "automotive_sector_report.docx",
  "html_content": "<!DOCTYPE html><html>...(full HTML with Chart.js)...</html>"
}
```

**Response (success):**
```json
{
  "status": "success",
  "path": "/Volumes/agentbricks/test/agent_reports/automotive_sector_report.docx",
  "filename": "automotive_sector_report.docx"
}
```

## Where Files Are Saved

```
/Volumes/agentbricks/test/agent_reports/
```

Configurable via the `REPORT_VOLUME_PATH` environment variable.

## Supported Chart Libraries

Any JavaScript charting library that renders to `<canvas>`:

- **Chart.js** (recommended - lightweight, CDN available)
- **Plotly.js** (via CDN)
- **D3.js** with canvas rendering
- Any library loaded via CDN `<script>` tag

## Testing

```bash
curl -X POST http://localhost:8000/convert-to-docx \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "test_chart_report.docx",
    "html_content": "<!DOCTYPE html><html><head><script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script></head><body><canvas id=\"myChart\"></canvas><script>new Chart(document.getElementById(\'myChart\'), {type:\'bar\',data:{labels:[\'A\',\'B\'],datasets:[{data:[10,20]}]}});</script></body></html>"
  }'
```

## Local Development

```bash
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REPORT_VOLUME_PATH` | `/Volumes/agentbricks/test/agent_reports` | Target volume path for saved reports |
