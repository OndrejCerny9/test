# Sector Report Agent

A Databricks App that acts as a **sub-agent** for a Databricks Supervisor Agent.  
The Supervisor Agent generates HTML reports with Chart.js visualizations, sends them to this app via the `/invocations` endpoint, and the app extracts chart data, renders charts with matplotlib, converts everything to a corporate-styled Word document (.docx), and saves the files to a Unity Catalog Volume.

## Purpose

This application serves as a **sub-agent tool** in a Supervisor Agent workflow:

1. The Supervisor Agent orchestrates report generation (data retrieval via Genie Space, analysis, HTML assembly with Chart.js).
2. Once the HTML report is ready, the agent calls this app's `/invocations` endpoint with a JSON message containing the filename and HTML content.
3. The app loads a corporate DOCX template (fonts, styles, header/footer, page layout).
4. It parses Chart.js configurations from `<script>` blocks.
5. Charts are rendered server-side as PNG images using matplotlib with the corporate color palette.
6. Text and tables are converted via `htmldocx`, chart images are inserted via `python-docx`.
7. A Table of Contents ("Obsah") is automatically inserted after the title with a page break.
8. Header/footer placeholders are replaced with the report title and current date.
9. The final .docx is saved to a Unity Catalog Volume using the Databricks SDK.
10. The app returns an SSE stream with the result (see Known Limitations below).

## Corporate Template

The generated Word documents use a corporate template (`app/template.docx`) with the following styling:

### Page Layout
- **Format**: A4 (21cm x 29.7cm)
- **Margins**: 1.5cm left/right, 2.2cm top, 2.0cm bottom
- **Header distance**: 1.0cm
- **Footer distance**: 0.8cm

### Fonts & Styles
| Style | Font | Size | Details |
|-------|------|------|---------|
| Normal (body) | Franklin Gothic Book | 10.5pt | Justified, 1.15 line spacing |
| Heading 1 | Franklin Gothic Book | 16pt | Bold, #245375 |
| Heading 2 | Franklin Gothic Book | 13pt | Bold, #245375 |
| Heading 3 | Franklin Gothic Book | 11pt | Bold, #245375 |
| Chart Title | Times New Roman | 10pt | Bold |
| Chart Source | Times New Roman | 9pt | Italic, #202020 |

### Header
- **Left**: Report title (extracted from `<h1>`)
- **Right**: Current month and year (e.g., "May 2026")
- **Style**: Franklin Gothic Book 10pt, small caps, #666666
- **Border**: Bottom border (0.5pt, #666666)

### Footer
- **Line**: Separator line paragraph (0.5pt, #666666) with spacing below
- **Content paragraph**:
  - Left: Page number field (#666666, 10pt)
  - Center: "Ekonomicke a Strategicke Analyzy" (Franklin Gothic Book 10pt, small caps, #666666)
  - Right: CSAS logo (floating/anchored, 2.19cm x 0.99cm, right-aligned to margin, -0.15cm vertical offset)

### Table of Contents
- Automatically inserted after the report title (`<h1>`)
- Uses "Obsah" as the heading (Heading 1 style)
- TOC field includes Heading 2 and Heading 3 levels (excludes title and "Obsah" itself)
- Followed by a page break
- Word will auto-populate entries when the document is opened and the field is updated

## How Chart Rendering Works

The agent generates HTML with Chart.js `<script>` blocks. Since there is no browser in the app container, charts are re-rendered with matplotlib:

1. Regex extracts `new Chart(...)` calls from `<script>` tags
2. Parses: chart type, labels, data arrays, dataset labels, colors, title
3. Renders equivalent chart with matplotlib using corporate color palette -> PNG bytes
4. Replaces `<canvas>` elements with text placeholders in the HTML
5. Converts cleaned HTML (text + tables) to DOCX via `htmldocx`
6. Post-processes the DOCX: finds placeholder paragraphs and replaces them with chart images
7. Adds bold chart title (Times New Roman 10pt) above each chart
8. Adds italic source citation "Zdroj: Vlastni zpracovani" (Times New Roman 9pt, #202020) below each chart

### Corporate Color Palette

Charts are rendered using these colors (in order of dataset priority):
1. `#4E5B6F` - Dark blue-gray (primary)
2. `#007EEA` - Bright blue
3. `#898989` - Medium gray
4. `#D6ECFF` - Light blue
5. `#A7D6FF` - Sky blue
6. `#FFDF43` - Yellow accent

Supported chart types: **bar**, **line**, **pie**, **doughnut** (with fallback to bar for unknown types).

## Endpoints

### `GET /health`
Health check endpoint.

### `POST /invocations` (Primary - used by Supervisor Agent)
The main endpoint called by the Databricks Supervisor Agent framework.

### `POST /convert-to-docx` (Direct testing)
Direct endpoint for testing without the Supervisor Agent framework.

## Where Files Are Saved

```
/Volumes/agentbricks/volumes/agent_reports/
```

Configurable via the `REPORT_VOLUME_PATH` environment variable.

## Known Limitations & Workarounds

### SSE Stream Parsing Issue
The Supervisor Agent currently cannot parse the SSE stream (reports "Tool returned no content"), even though conversion completes successfully.

**Workaround:** Agent instructions assume success if tool returns no content.

### Other Limitations
- Supported chart types: bar, line, pie, doughnut (others fall back to bar)
- Chart.js extraction requires simple data arrays (no JS callbacks/functions)
- Color arrays per-bar use only the first color
- No external images, no CSS styling preserved
- TOC auto-update: Must be updated manually in Word (right-click -> "Update Field")

## Deployment

**App Name:** `agent-sector-report`  
**URL:** `agent-sector-report-3863256616093854.14.azure.databricksapps.com`

### Permissions Required
The app's service principal (`fa36362a-e6d6-49ad-9401-86a16796ff54`) needs:
- `USE CATALOG` on `agentbricks`
- `USE SCHEMA` on `agentbricks.volumes`
- `READ VOLUME` + `WRITE VOLUME` on `agentbricks.volumes.agent_reports`

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
|-- app/
|   |-- __init__.py
|   |-- main.py                    # FastAPI app with /invocations and /convert-to-docx
|   |-- template.docx             # Corporate DOCX template (styles, header/footer, page setup)
|   +-- tools/
|       |-- __init__.py
|       +-- html_to_docx_converter.py  # Chart extraction, rendering, TOC, DOCX assembly
|-- docs/
|   |-- architecture.md            # System architecture diagram
|   +-- agent_tool_contract.md     # Supervisor Agent integration contract
|-- app.yaml                       # Databricks Apps configuration
|-- requirements.txt               # Python dependencies
|-- start.sh                       # Startup script
+-- README.md                      # This file
```
