# Agent Tool Contract

## Overview

**App Name:** `agent-sector-report`
**Endpoint:** `POST /invocations`
**Volume:** `/Volumes/agentbricks/volumes/agent_reports/`

## Input Format

The Supervisor Agent sends a message with `content` containing ONLY a JSON object:

```json
{"filename": "automotive_report.docx", "html_content": "<!DOCTYPE html><html>...</html>"}
```

## What the App Does

1. Loads corporate template (Franklin Gothic Book, styled header/footer)
2. Replaces header placeholders with report title and date
3. Extracts Chart.js configs from `<script>` tags via regex
4. Generates **native Word chart objects** (OOXML DrawingML) for each chart
5. Creates embedded Excel worksheets with source data
6. Converts HTML text/tables/headings via htmldocx
7. Inserts Table of Contents ("Obsah") after title (H2/H3 levels)
8. Applies corporate font (Franklin Gothic Book) on all text
9. Injects chart parts into the .docx ZIP (chart XML + Excel + relationships)
10. Saves to UC Volume via Databricks SDK

## Output

Charts are **native editable Word chart objects**:
- Double-click to edit data in Excel
- Resizable without quality loss
- Corporate color palette applied automatically

## Generated Document Structure

```
Page 1: Report Title (H1)
Page 2: Obsah (Table of Contents)
         - H2/H3 headings with page numbers
Page 3+: Report Content
         - Chapters with native charts, tables, analysis
```

Every page has:
- Header: title (left) + date (right), small caps #666666, bottom border
- Footer: page number (left) + "Ekonomicke a Strategicke Analyzy" (center) + CSAS logo (right)

## Chart.js Rules (for Supervisor Agent)

```
CHART RULES (critical - parsed via regex, not executed):
- Each <canvas> MUST have a unique id
- Supported: bar, line, pie, doughnut
- labels: simple array of strings
- datasets[].data: simple array of numbers
- datasets[].label: simple string
- datasets[].backgroundColor: single rgba() or hex color
- Title in: options.plugins.title.text
- No JS callbacks, functions, or dynamic expressions
- No color arrays - one color per dataset
- All charts in single <script> at end of <body>

Patterns supported:
  new Chart(document.getElementById('id'), {...});
  const ctx = document.getElementById('id').getContext('2d'); new Chart(ctx, {...});
```

## Response Handling

**Known issue:** Agent reports "Tool returned no content" despite success.

**Workaround:** If tool returns no content/empty, assume success.
File path: `/Volumes/agentbricks/volumes/agent_reports/{filename}`

## Supervisor Agent Instructions

```
You are a sector report analyst. When a user asks for a report:

1. GATHER DATA from Genie Space.

2. GENERATE HTML with Chart.js (follow CHART RULES above).
   - Use corporate colors: #4E5B6F, #007EEA, #898989, #D6ECFF, #A7D6FF, #FFDF43
   - Structure: Title (h1) > sections (h2) > charts + tables + analysis > Conclusion (h2)
   - Do NOT include a Table of Contents - it is generated automatically

3. SAVE: Send ONLY this JSON:
   {"filename": "name.docx", "html_content": "<full HTML>"}

   The app converts charts to native editable Word objects and applies corporate styling.

4. CONFIRM with file path. If no response, assume success:
   /Volumes/agentbricks/volumes/agent_reports/{filename}
```

## App Description (for agent tool config)

```
Converts HTML reports with Chart.js charts to corporate-styled Word documents (.docx)
with native editable charts. Send a message containing ONLY a JSON object with "filename"
(ending in .docx) and "html_content" (the complete HTML string with Chart.js).
Charts are converted to native Word chart objects (editable in Excel).
A Table of Contents is inserted automatically. Supported chart types: bar, line, pie, doughnut.
If no response is returned, the conversion succeeded and the file is at
/Volumes/agentbricks/volumes/agent_reports/{filename}.
```
