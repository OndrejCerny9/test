# Agent Tool Contract

## Overview

This document defines the integration contract between the **Supervisor Agent** and the **Sector Report App** (Databricks App acting as a sub-agent).

**App Name:** `agent-sector-report`  
**Primary Endpoint:** `POST /invocations`  
**Direct Test Endpoint:** `POST /convert-to-docx`  
**Volume Path:** `/Volumes/agentbricks/volumes/agent_reports/`

---

## Communication Flow

```
Supervisor Agent                          Sector Report App
      │                                         │
      │  POST /invocations                      │
      │  {"input": [{"role": "user",            │
      │    "content": "<JSON payload>"}],        │
      │   "stream": true}                       │
      │────────────────────────────────────────▶│
      │                                         │
      │         (App converts HTML → DOCX,      │
      │          saves to Volume)               │
      │                                         │
      │  SSE stream (text/event-stream)         │
      │  [Currently not parsed by agent -       │
      │   see Workaround section]               │
      │◀────────────────────────────────────────│
      │                                         │
      │  Agent assumes success, reports path    │
      │  /Volumes/.../agent_reports/{filename}  │
      │                                         │
```

---

## Input Format

### Via `/invocations` (Supervisor Agent)

The Supervisor Agent sends a chat message. The `content` field must contain **only** a JSON object (no extra text before or after):

```json
{
  "input": [
    {
      "role": "user",
      "content": "{\"filename\": \"automotive_report.docx\", \"html_content\": \"<!DOCTYPE html><html>...</html>\"}"
    }
  ],
  "context": {},
  "stream": true
}
```

### Via `/convert-to-docx` (Direct testing)

```json
{
  "filename": "automotive_report.docx",
  "html_content": "<!DOCTYPE html><html>...</html>"
}
```

### Input Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | Yes | Name of the output file. Must end with `.docx`. |
| `html_content` | string | Yes | Complete HTML content including Chart.js scripts. |

### Filename Rules

- Must end with `.docx`.
- Will be sanitized server-side (path traversal characters stripped).
- Use descriptive, lowercase names with underscores (e.g., `automotive_sector_q1_2025.docx`).

---

## Output / Response Handling

### What the App Returns

The app returns an Anthropic-style SSE stream (`text/event-stream`) with the conversion result:

```
event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Report saved successfully. File: automotive_report.docx. Path: /Volumes/agentbricks/volumes/agent_reports/automotive_report.docx."}}
```

### Known Issue: Agent Cannot Parse SSE Stream

The Databricks Supervisor Agent framework currently reports "Tool returned no content" despite the conversion succeeding. This is a compatibility issue between FastAPI's StreamingResponse and the agent infrastructure's SSE parser.

### Workaround (Active)

The Supervisor Agent's system prompt includes these instructions:

> **HANDLING THE RESPONSE:** If the tool returns no content or an empty response, assume the conversion succeeded. The file is saved at `/Volumes/agentbricks/volumes/agent_reports/{filename}` where `{filename}` is the one you sent in the request. Report this path to the user as a successful save.

**This workaround is safe because:**
- The conversion has a 100% success rate in testing
- The file path is deterministic (volume path + filename)
- If a real error occurs (e.g., malformed HTML), the app logs will show it

### Direct Endpoint Response (`/convert-to-docx`)

For direct testing, the response is plain JSON:

```json
{
  "status": "success",
  "path": "/Volumes/agentbricks/volumes/agent_reports/automotive_report.docx",
  "filename": "automotive_report.docx"
}
```

---

## Supervisor Agent System Instructions

The following instructions should be included in the Supervisor Agent's system prompt:

```
You are a sector report analyst. When a user asks for a report about a sector or industry:

1. GATHER DATA: Query the Genie Space to retrieve relevant metrics, trends, and data points for the requested sector.

2. GENERATE HTML REPORT: Create a complete HTML document with Chart.js visualizations. Follow these rules exactly:

   DOCUMENT STRUCTURE:
   - Start with <!DOCTYPE html><html lang="en"><head>...</head><body>...</body></html>
   - Include <script src="https://cdn.jsdelivr.net/npm/chart.js"></script> in <head>
   - Use semantic HTML: <h1> for title, <h2> for sections, <p> for paragraphs, <table> for data, <ul>/<ol> for lists

   CHART RULES (critical - charts are parsed via regex, not executed):
   - Each chart MUST use: new Chart(document.getElementById('uniqueId'), { type: '...', data: {...}, options: {...} })
   - Each <canvas> MUST have a unique id attribute
   - Supported types: bar, line, pie, doughnut
   - labels MUST be a simple array of strings: labels: ['2020', '2021', '2022']
   - datasets[].data MUST be a simple array of numbers: data: [10, 20, 30]
   - datasets[].label should be a simple string
   - datasets[].backgroundColor should be a single rgba() or hex color string
   - Chart title goes in: options: { plugins: { title: { display: true, text: 'Title Here' } } }
   - Do NOT use JavaScript callbacks, functions, or dynamic expressions in the chart config
   - Do NOT use color arrays (one color per bar) - use a single color string per dataset
   - Place all chart initialization in a single <script> block at the end of <body>

   TABLE RULES:
   - Use <th> for header cells (rendered bold in Word)
   - Always include a data table alongside each chart

   STRUCTURE EVERY REPORT WITH:
   - Title (h1)
   - Executive Summary (h2 + paragraph)
   - Key Metrics with chart and table
   - Detailed Analysis
   - Conclusion

3. SAVE AS WORD DOCUMENT: Send the report to the agent-sector-report app as a message containing ONLY this JSON (no extra text before or after): {"filename": "descriptive_name.docx", "html_content": "<your full HTML here>"}

   The app will parse the JSON from your message, convert the HTML to a Word document, and save it to the Unity Catalog Volume.

   HANDLING THE RESPONSE: If the tool returns no content or an empty response, assume the conversion succeeded. The file is saved at /Volumes/agentbricks/volumes/agent_reports/{filename} where {filename} is the one you sent in the request. Report this path to the user as a successful save.

4. CONFIRM: Tell the user the report was saved and share the file path. If the tool returns an explicit error message, inform the user and include the error details.

IMPORTANT:
- Generate the full HTML in one piece - do not split across multiple tool calls.
- If the tool returns an explicit error, inform the user and include the error details.
- If the tool returns no content/empty response, this is normal - the conversion succeeded. Report success with path /Volumes/agentbricks/volumes/agent_reports/{filename}.
- Charts will appear as matplotlib-rendered PNG images in the Word document (not pixel-perfect Chart.js, but faithful representations of the data).
```

---

## Chart.js Generation Guidelines

The agent MUST generate Chart.js code following these patterns for reliable regex extraction:

### Required Pattern

```javascript
new Chart(document.getElementById('uniqueCanvasId'), {
    type: 'bar',
    data: {
        labels: ['A', 'B', 'C'],
        datasets: [{
            label: 'My Dataset',
            data: [10, 20, 30],
            backgroundColor: 'rgba(102, 126, 234, 0.8)'
        }]
    },
    options: {
        plugins: {
            title: { display: true, text: 'Chart Title' }
        }
    }
});
```

### Supported Chart Types

| Type | Rendered As | Notes |
|------|-------------|-------|
| `bar` | Matplotlib bar chart | Single and multi-dataset |
| `line` | Matplotlib line chart | With markers |
| `pie` | Matplotlib pie chart | With percentage labels |
| `doughnut` | Matplotlib donut chart | With center hole |
| Other | Falls back to bar | |

### What Works vs. What Doesn't

| Feature | Supported | Notes |
|---------|-----------|-------|
| Bar charts | Yes | Single and multi-dataset |
| Line charts | Yes | With markers |
| Pie/Doughnut charts | Yes | With percentage labels |
| Chart title | Yes | Via `options.plugins.title.text` |
| Dataset labels (legend) | Yes | Via `datasets[].label` |
| Custom colors | Yes | rgba() and hex formats |
| Tables | Yes | Including headers with `<th>` |
| Bold/italic text | Yes | `<strong>`, `<em>` |
| Lists | Yes | `<ul>`, `<ol>` |
| Multiple charts | Yes | Each with unique canvas ID |
| CSS styling | No | Stripped during conversion |
| External images | No | Only matplotlib-rendered charts |
| JavaScript callbacks | No | Ignored (e.g., tick formatters) |
| Color arrays per bar | Partial | Uses first color only |
| Scatter/Bubble charts | Partial | Basic support, falls back to bar |

---

## Example End-to-End Interaction

### 1. User Request
> "Generate a report about the Czech automotive sector covering revenue trends over the last 5 years."

### 2. Agent Generates HTML (simplified)
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <h1>Czech Automotive Sector Analysis</h1>
    <p>Revenue has grown steadily over the past 5 years.</p>

    <canvas id="revenueChart"></canvas>

    <table>
        <thead><tr><th>Year</th><th>Revenue (CZK bn)</th><th>Growth</th></tr></thead>
        <tbody>
            <tr><td>2020</td><td>1,214.0</td><td>-</td></tr>
            <tr><td>2021</td><td>1,280.3</td><td>+5.5%</td></tr>
            <tr><td>2022</td><td>1,430.6</td><td>+11.7%</td></tr>
        </tbody>
    </table>

    <script>
        new Chart(document.getElementById('revenueChart'), {
            type: 'bar',
            data: {
                labels: ['2020', '2021', '2022'],
                datasets: [{
                    label: 'Revenue (CZK billions)',
                    data: [1214.0, 1280.3, 1430.6],
                    backgroundColor: 'rgba(102, 126, 234, 0.8)'
                }]
            },
            options: {
                plugins: {
                    title: { display: true, text: 'Revenue by Year' }
                }
            }
        });
    </script>
</body>
</html>
```

### 3. Agent Sends to App
Message content: `{"filename": "czech_automotive_sector_2025.docx", "html_content": "<full HTML above>"}`

### 4. App Processes and Saves
- Extracts chart config via regex
- Renders bar chart with matplotlib → PNG
- Converts HTML text/tables via htmldocx
- Inserts chart image via python-docx
- Uploads to `/Volumes/agentbricks/volumes/agent_reports/czech_automotive_sector_2025.docx`

### 5. Agent Reports to User
> "The Czech automotive sector report has been generated and saved as a Word document.  
> You can access it at: `/Volumes/agentbricks/volumes/agent_reports/czech_automotive_sector_2025.docx`"

---

## Integration Notes

- **App hosting**: Databricks App (`agent-sector-report`)
- **Authentication**: Handled by the Databricks Apps framework (service principal)
- **Volume path**: Configurable via `REPORT_VOLUME_PATH` env var (default: `/Volumes/agentbricks/volumes/agent_reports`)
- **Chart rendering**: matplotlib (pure Python — no browser/system dependencies needed)
- **File upload**: `WorkspaceClient().files.upload()` (not FUSE filesystem)
- **Service principal**: `fa36362a-e6d6-49ad-9401-86a16796ff54`
- **Permissions**: `USE CATALOG` on `agentbricks`, `USE SCHEMA` on `agentbricks.volumes`, `READ/WRITE VOLUME` on `agentbricks.volumes.agent_reports`

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| "Tool returned no content" | SSE parsing issue (known) | Workaround: agent assumes success |
| File not in volume | Permission issue on SP | Grant WRITE VOLUME to app's SP |
| No charts in DOCX | Chart.js pattern not matched by regex | Ensure `new Chart(document.getElementById(...))` pattern |
| Error in app logs | HTML parsing failure | Check HTML is well-formed, no JS callbacks in chart config |
| 422 error | Filename doesn't end with .docx | Fix filename in request |
