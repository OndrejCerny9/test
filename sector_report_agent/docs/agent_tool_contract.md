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
      |                                         |
      |  POST /invocations                      |
      |  {"input": [{"role": "user",            |
      |    "content": "<JSON payload>"}],        |
      |   "stream": true}                       |
      |---------------------------------------->|
      |                                         |
      |         (App converts HTML -> DOCX,     |
      |          applies corporate template,    |
      |          inserts TOC, saves to Volume)  |
      |                                         |
      |  SSE stream (text/event-stream)         |
      |  [Currently not parsed by agent -       |
      |   see Workaround section]               |
      |<----------------------------------------|
      |                                         |
      |  Agent assumes success, reports path    |
      |  /Volumes/.../agent_reports/{filename}  |
      |                                         |
```

---

## Input Format

### Via `/invocations` (Supervisor Agent)

The `content` field must contain **only** a JSON object (no extra text):

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

---

## What the App Does with the Input

1. **Loads corporate template** (`template.docx`) with pre-defined styles, page setup, header/footer
2. **Replaces header placeholders**: `{{REPORT_TITLE}}` with the `<h1>` text, `{{REPORT_DATE}}` with current month/year
3. **Extracts Chart.js configs** from `<script>` tags via regex
4. **Renders charts** with matplotlib using corporate color palette -> PNG images
5. **Converts HTML** (text, tables, headings, lists) via htmldocx
6. **Inserts Table of Contents** ("Obsah") after the title, covering Heading 2-3 levels, followed by a page break
7. **Replaces chart placeholders** with: bold chart title + PNG image + italic source citation
8. **Applies corporate font** (Franklin Gothic Book) on all text where htmldocx left font unset
9. **Saves to UC Volume** via Databricks SDK `files.upload()`

---

## Output / Response Handling

### Known Issue: Agent Cannot Parse SSE Stream

The Supervisor Agent reports "Tool returned no content" despite conversion succeeding.

### Workaround (Active)

The Supervisor Agent's system prompt includes:

> **HANDLING THE RESPONSE:** If the tool returns no content or an empty response, assume the conversion succeeded. The file is saved at `/Volumes/agentbricks/volumes/agent_reports/{filename}` where `{filename}` is the one you sent in the request.

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
   - Two chart initialization patterns are supported. Use EITHER:
     Pattern A (direct): new Chart(document.getElementById('myChart'), { type: 'bar', data: {...}, options: {...} });
     Pattern B (variable): const ctx = document.getElementById('myChart').getContext('2d'); new Chart(ctx, { type: 'bar', data: {...}, options: {...} });

   CORPORATE COLOR PALETTE (use these colors for charts):
   - Primary series: rgba(78, 91, 111, 0.8) - dark blue-gray (#4E5B6F)
   - Secondary series: rgba(0, 126, 234, 0.8) - bright blue (#007EEA)
   - Tertiary series: rgba(137, 137, 137, 0.8) - gray (#898989)
   - Additional: rgba(214, 236, 255, 0.8), rgba(167, 214, 255, 0.8), rgba(255, 223, 67, 0.8)

   TABLE RULES:
   - Use <th> for header cells (rendered bold in Word)
   - Always include a data table alongside each chart

   REPORT STRUCTURE:
   - Title (h1) - this becomes the header text in the Word document
   - Executive Summary (h2) - use bold lead sentences followed by explanation text
   - Topic chapters (h2) - each with analysis text, charts, and data tables
   - Conclusion (h2)

3. SAVE AS WORD DOCUMENT: Send the report to the agent-sector-report app as a message containing ONLY this JSON (no extra text before or after): {"filename": "descriptive_name.docx", "html_content": "<your full HTML here>"}

   The app will:
   - Apply the corporate template (Franklin Gothic Book font, styled headings, page margins)
   - Populate the header with the report title and current date
   - Insert a Table of Contents ("Obsah") after the title covering all H2/H3 sections
   - Render charts with matplotlib using the corporate color palette
   - Add bold chart titles and italic source citations ("Zdroj: Vlastni zpracovani") automatically
   - Save to the Unity Catalog Volume

   HANDLING THE RESPONSE: If the tool returns no content or an empty response, assume the conversion succeeded. The file is saved at /Volumes/agentbricks/volumes/agent_reports/{filename} where {filename} is the one you sent in the request. Report this path to the user as a successful save.

4. CONFIRM: Tell the user the report was saved and share the file path. If the tool returns an explicit error message, inform the user and include the error details.

IMPORTANT:
- Generate the full HTML in one piece - do not split across multiple tool calls.
- If the tool returns an explicit error, inform the user and include the error details.
- If the tool returns no content/empty response, this is normal - the conversion succeeded. Report success with path /Volumes/agentbricks/volumes/agent_reports/{filename}.
- Charts will appear as matplotlib-rendered PNG images styled with the corporate color palette. Chart titles and source citations are added automatically by the app.
- The Word document will use corporate styling: Franklin Gothic Book body text, colored headings (#245375), A4 page with 1.5cm side margins.
- A Table of Contents page ("Obsah") is generated automatically - no need to include it in the HTML.
```

---

## Chart.js Generation Guidelines

### Supported Patterns

**Pattern 1: Direct (recommended)**
```javascript
new Chart(document.getElementById('uniqueCanvasId'), {
    type: 'bar',
    data: {
        labels: ['A', 'B', 'C'],
        datasets: [{
            label: 'My Dataset',
            data: [10, 20, 30],
            backgroundColor: 'rgba(78, 91, 111, 0.8)'
        }]
    },
    options: {
        plugins: {
            title: { display: true, text: 'Chart Title' }
        }
    }
});
```

**Pattern 2: Variable-based**
```javascript
const ctx = document.getElementById('uniqueCanvasId').getContext('2d');
new Chart(ctx, {
    type: 'bar',
    data: {
        labels: ['A', 'B', 'C'],
        datasets: [{
            label: 'My Dataset',
            data: [10, 20, 30],
            backgroundColor: 'rgba(78, 91, 111, 0.8)'
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

### What Works vs. What Does Not

| Feature | Supported | Notes |
|---------|-----------|-------|
| Simple data arrays | Yes | `data: [10, 20, 30]` |
| Negative numbers | Yes | `data: [-5, 10, -3]` |
| Multiple datasets | Yes | Grouped bars, multiple lines |
| Dataset labels | Yes | Shown in legend |
| rgba() colors | Yes | Per-dataset |
| Hex colors | Yes | Per-dataset |
| Chart title via plugins | Yes | Shown above chart |
| JS callbacks | No | Not executed |
| Dynamic expressions | No | Not evaluated |
| Color arrays | No | Use single color per dataset |
| External data sources | No | Data must be inline |

---

## Generated Document Structure

The final Word document has this structure:

```
Page 1: Report Title (H1)
Page 2: Obsah (Table of Contents)
         - Lists all H2/H3 headings with page numbers
         - (auto-populated by Word on field update)
Page 3+: Report Content
         - Executive Summary
         - Chapters with charts, tables, analysis
         - Conclusion
```

Every page includes:
- **Header**: Report title (left) + date (right), small caps, gray, bottom border
- **Footer**: Page number (left) + "Ekonomicke a Strategicke Analyzy" (center) + CSAS logo (right)
