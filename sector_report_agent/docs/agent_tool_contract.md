# Agent Tool Contract

## Tool Definition

**Tool Name:** `convert_html_to_docx`

**Description:** Parses Chart.js configurations from HTML, renders charts server-side with matplotlib, converts the report to a Word document (.docx), and saves it to a Unity Catalog Volume.

**Endpoint:** `POST /convert-to-docx`

**App Name:** `agent-sector-report`

---

## Input Schema

```json
{
  "filename": "automotive_report.docx",
  "html_content": "<!DOCTYPE html><html>...</html>"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `filename` | string | Yes | Name of the output file. Must end with `.docx`. |
| `html_content` | string | Yes | Complete HTML content including Chart.js scripts. |

### Filename Rules

- Must end with `.docx`.
- Will be sanitized server-side (path traversal characters stripped).
- Use descriptive, lowercase names with underscores (e.g., `automotive_sector_q1_2025.docx`).

---

## Output Schema

### Success Response (200)

```json
{
  "status": "success",
  "path": "/Volumes/agentbricks/volumes/agent_reports/automotive_report.docx",
  "filename": "automotive_report.docx"
}
```

### Conversion Error Response (422)

```json
{
  "detail": "HTML to DOCX conversion failed: [error details]"
}
```

### Save Error Response (500)

```json
{
  "detail": "Failed to write report to /Volumes/..."
}
```

---

## Supervisor Agent Instructions

Include the following in the Supervisor Agent system prompt:

> You are responsible for generating sector reports as complete HTML documents with Chart.js
> visualizations. The app will parse your Chart.js configurations and render them server-side
> with matplotlib, so charts will appear as images in the final Word document.
>
> After generating the HTML report, call the `convert_html_to_docx` tool.
> Do not claim that the report was saved unless the tool returns status = "success".

### Chart.js Generation Guidelines

The agent MUST generate Chart.js code following these patterns for reliable extraction:

1. **Include Chart.js via CDN** in `<head>` (not required for rendering, but keeps HTML valid):
   ```html
   <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
   ```

2. **Use `<canvas>` elements** with unique IDs:
   ```html
   <div style="width: 800px; height: 400px;">
       <canvas id="myChart"></canvas>
   </div>
   ```

3. **Initialize charts with `new Chart(document.getElementById('id'), {...})`**:
   ```javascript
   new Chart(document.getElementById('myChart'), {
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

4. **Supported chart types**: `bar`, `line`, `pie`, `doughnut`

5. **Extracted fields** (must be present for chart to render):
   - `type`: Chart type string
   - `labels`: Array of string labels
   - `data`: Array of numeric values in each dataset
   - `label` (optional): Dataset label string
   - `backgroundColor` (optional): Color string (rgba or hex)
   - `text` in options.plugins.title (optional): Chart title

6. **Text content** should use semantic HTML: `<h1>`-`<h6>`, `<p>`, `<table>`, `<ul>/<ol>`, `<strong>`, `<em>`

7. **Tables** should use `<th>` for headers (rendered bold in Word)

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
| Scatter/Bubble charts | Partial | Basic support only |

### Example HTML with Chart

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <h1>Automotive Sector Revenue Analysis</h1>
    <p>Revenue has grown steadily over the past 5 years.</p>

    <div style="width: 800px; height: 400px;">
        <canvas id="revenueChart"></canvas>
    </div>

    <h2>Data Summary</h2>
    <table>
        <thead>
            <tr><th>Year</th><th>Revenue (CZK bn)</th><th>Growth</th></tr>
        </thead>
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

### Additional Agent Instructions

> - Always generate a descriptive filename (e.g., `automotive_sector_may_2025.docx`).
> - Include the complete HTML in a single tool call — do not split across calls.
> - Charts will appear as static matplotlib-rendered images in the Word document.
> - If the tool returns an error, inform the user and include the error message.
> - The saved report path from the response can be shared with the user for direct access.
> - Always include a data table alongside each chart for accessibility.
> - Use simple color values (rgba or hex) — complex color arrays per-bar are supported but only the first color is used.

---

## Example Interaction

### Agent calls tool:

```json
{
  "name": "convert_html_to_docx",
  "arguments": {
    "filename": "automotive_sector_report_2025.docx",
    "html_content": "<!DOCTYPE html><html><head><script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script></head><body><h1>Automotive Sector</h1><div><canvas id=\"chart1\"></canvas></div><script>new Chart(document.getElementById('chart1'),{type:'bar',data:{labels:['2020','2021','2022'],datasets:[{label:'Revenue',data:[1214,1280,1430],backgroundColor:'rgba(102,126,234,0.8)'}]},options:{plugins:{title:{display:true,text:'Revenue Trend'}}}});</script></body></html>"
  }
}
```

### Tool response:

```json
{
  "status": "success",
  "path": "/Volumes/agentbricks/volumes/agent_reports/automotive_sector_report_2025.docx",
  "filename": "automotive_sector_report_2025.docx"
}
```

### Agent response to user:

> "The automotive sector report has been generated and saved as a Word document.
> You can access it at: `/Volumes/agentbricks/volumes/agent_reports/automotive_sector_report_2025.docx`"

---

## Integration Notes

- The tool endpoint is hosted as a Databricks App (`agent-sector-report`).
- Authentication is handled by the Databricks Apps framework.
- The volume path is configurable via `REPORT_VOLUME_PATH` environment variable.
- Default volume: `/Volumes/agentbricks/volumes/agent_reports`
- Charts are rendered with matplotlib (pure Python — no browser/system dependencies).
- File upload uses `WorkspaceClient().files.upload()` (not FUSE filesystem).
- The app's service principal needs `USE CATALOG`, `USE SCHEMA`, `READ VOLUME`, and `WRITE VOLUME` permissions.
