# Sector Report Agent

A Databricks App that exposes an HTTP tool endpoint for a Databricks Supervisor Agent.  
The Supervisor Agent generates HTML reports with charts, and this app saves the generated HTML files into a Unity Catalog Volume.

## Purpose

This application serves as a **tool endpoint** for a Supervisor Agent workflow:

1. The Supervisor Agent orchestrates report generation (data retrieval, chart creation, HTML assembly).
2. Once the HTML report is ready, the agent calls this app's `/save-html-report` endpoint.
3. The app persists the HTML file to a Unity Catalog Volume for downstream access.

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

### `POST /save-html-report`

Saves an HTML report to the configured Unity Catalog Volume.

**Request Body:**
```json
{
  "filename": "automotive_sector_report.html",
  "html_content": "<html><head><title>Report</title></head><body><h1>Automotive Sector</h1></body></html>"
}
```

**Response (success):**
```json
{
  "status": "success",
  "path": "/Volumes/agentbricks/test/agent_reports/automotive_sector_report.html",
  "filename": "automotive_sector_report.html"
}
```

**Response (error):**
```json
{
  "detail": "Failed to write report to /Volumes/..."
}
```

## Where Files Are Saved

Reports are saved to the Unity Catalog Volume at:

```
/Volumes/agentbricks/test/agent_reports/
```

This path is configurable via the `REPORT_VOLUME_PATH` environment variable.

## Testing

### Test Health Endpoint

```bash
curl -X GET http://localhost:8000/health
```

### Test Save Report Endpoint

```bash
curl -X POST http://localhost:8000/save-html-report \
  -H "Content-Type: application/json" \
  -d '{
    "filename": "test_report.html",
    "html_content": "<html><body><h1>Test</h1></body></html>"
  }'
```

## Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `REPORT_VOLUME_PATH` | `/Volumes/agentbricks/test/agent_reports` | Target volume path for saved reports |
