# Agent Tool Contract

## Tool Definition

**Tool Name:** `convert_html_to_docx`

**Description:** Renders an HTML report (including JavaScript-based charts like Chart.js) in a headless browser, converts it to a Word document (.docx), and saves it to the configured Unity Catalog Volume. Use this tool after assembling the final HTML report content with charts.

**Endpoint:** `POST /convert-to-docx`

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
  "path": "/Volumes/agentbricks/test/agent_reports/automotive_report.docx",
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
> visualizations. The app will render your HTML in a headless browser, so Chart.js charts
> will be fully rendered and converted to images in the final Word document.
>
> After generating the HTML report, call the `convert_html_to_docx` tool.
> Do not claim that the report was saved unless the tool returns status = "success".

### HTML + Chart.js Generation Guidelines

The agent MUST generate a **complete, self-contained HTML document** for reliable rendering:

1. **Include Chart.js via CDN** in the `<head>`:
   ```html
   <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
   ```

2. **Use `<canvas>` elements** for charts with explicit dimensions:
   ```html
   <div style="width: 800px; height: 400px;">
       <canvas id="myChart"></canvas>
   </div>
   ```

3. **Initialize charts in a `<script>` block** at the end of `<body>`:
   ```html
   <script>
       new Chart(document.getElementById('myChart'), {
           type: 'bar',
           data: { labels: [...], datasets: [...] },
           options: { responsive: true, maintainAspectRatio: false }
       });
   </script>
   ```

4. **Supported chart types**: bar, line, pie, doughnut, radar, polarArea, scatter, bubble

5. **Text content** should use semantic HTML: `<h1>`-`<h6>`, `<p>`, `<table>`, `<ul>/<ol>`, `<strong>`, `<em>`

6. **Tables** should use `<th>` for headers (rendered bold in Word)

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
            <tr><td>2023</td><td>1,716.5</td><td>+20.0%</td></tr>
            <tr><td>2024</td><td>1,795.0</td><td>+4.6%</td></tr>
        </tbody>
    </table>
    
    <script>
        new Chart(document.getElementById('revenueChart'), {
            type: 'bar',
            data: {
                labels: ['2020', '2021', '2022', '2023', '2024'],
                datasets: [{
                    label: 'Revenue (CZK billions)',
                    data: [1214.0, 1280.3, 1430.6, 1716.5, 1795.0],
                    backgroundColor: 'rgba(102, 126, 234, 0.8)',
                    borderColor: 'rgba(102, 126, 234, 1)',
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'top' } }
            }
        });
    </script>
</body>
</html>
```

### Additional Agent Instructions

> - Always generate a descriptive filename (e.g., `automotive_sector_may_2025.docx`).
> - Include the complete HTML in a single tool call — do not split across calls.
> - Charts will be rendered as static images in the Word document.
> - If the tool returns an error, inform the user and include the error message.
> - The saved report path from the response can be shared with the user for direct access.
> - Do NOT use external image URLs — all chart data must be inline in the HTML.

---

## Integration Notes

- The tool endpoint is hosted as a Databricks App.
- Authentication is handled by the Databricks Apps framework.
- The volume path is configurable via `REPORT_VOLUME_PATH` environment variable.
- Default volume: `/Volumes/agentbricks/test/agent_reports`
- **Playwright + Chromium** renders JavaScript charts before conversion.
- The headless browser requires network access to `cdn.jsdelivr.net` for Chart.js CDN.
- Static HTML (no scripts) is converted directly without browser rendering.
