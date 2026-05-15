# Agent Tool Contract

## Tool Definition

**Tool Name:** `save_html_report`

**Description:** Saves a generated HTML report file to the configured Unity Catalog Volume. Use this tool after assembling the final HTML report content.

**Endpoint:** `POST /save-html-report`

---

## Input Schema

```json
{
  "filename": "automotive_report.html",
  "html_content": "<html>...</html>"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | Yes | Name of the output file. Must end with `.html`. |
| `html_content` | string | Yes | Complete HTML content of the report. |

### Filename Rules

- Must end with `.html`.
- Will be sanitized server-side (path traversal characters stripped).
- Use descriptive, lowercase names with underscores (e.g., `automotive_sector_q1_2025.html`).

---

## Output Schema

### Success Response

```json
{
  "status": "success",
  "path": "/Volumes/agentbricks/test/agent_reports/automotive_report.html",
  "filename": "automotive_report.html"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Always `"success"` on successful save. |
| `path` | string | Full path where the file was saved. |
| `filename` | string | Sanitized filename that was used. |

### Error Response

```json
{
  "detail": "Failed to write report to /Volumes/agentbricks/test/agent_reports/report.html: [error details]"
}
```

HTTP Status: `500 Internal Server Error`

---

## Supervisor Agent Instructions

Include the following in the Supervisor Agent system prompt:

> When the report HTML is generated, always call the save_html_report tool.
> Do not claim that the report was saved unless the tool returns status = success.

### Additional Recommended Instructions

> - Always generate a descriptive filename that reflects the report content (e.g., `automotive_sector_may_2025.html`).
> - If the tool returns an error, inform the user that the report could not be saved and include the error message.
> - Do not modify the HTML content after receiving confirmation of a successful save.
> - The saved report path from the response can be shared with the user for direct access.

---

## Example Interaction

### Agent generates report and calls tool:

**Tool Call:**
```json
{
  "name": "save_html_report",
  "arguments": {
    "filename": "automotive_sector_report_2025.html",
    "html_content": "<!DOCTYPE html><html><head><title>Automotive Sector Report</title><style>body{font-family:sans-serif;}</style></head><body><h1>Automotive Sector Analysis</h1><p>Key findings...</p></body></html>"
  }
}
```

**Tool Response:**
```json
{
  "status": "success",
  "path": "/Volumes/agentbricks/test/agent_reports/automotive_sector_report_2025.html",
  "filename": "automotive_sector_report_2025.html"
}
```

### Agent response to user:

> "The automotive sector report has been generated and saved successfully.  
> You can access it at: `/Volumes/agentbricks/test/agent_reports/automotive_sector_report_2025.html`"

---

## Integration Notes

- The tool endpoint is hosted as a Databricks App.
- Authentication is handled by the Databricks Apps framework.
- The volume path is configurable via `REPORT_VOLUME_PATH` environment variable.
- Default volume: `/Volumes/agentbricks/test/agent_reports`
