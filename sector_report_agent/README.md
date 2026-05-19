# Sector Report Agent

A Databricks App that acts as a **sub-agent** for a Databricks Supervisor Agent.
Converts HTML reports with Chart.js to corporate-styled Word documents (.docx) with **native editable charts**.

## Purpose

1. Supervisor Agent generates HTML report with Chart.js visualizations
2. Sends to this app via `/invocations` endpoint
3. App loads corporate DOCX template (fonts, styles, header/footer)
4. Parses Chart.js configs from `<script>` blocks via regex
5. Converts charts to **native Word chart objects** (OOXML DrawingML) with embedded Excel data
6. Converts text/tables via htmldocx
7. Inserts Table of Contents ("Obsah") after the title
8. Replaces header placeholders with report title and date
9. Saves to UC Volume via Databricks SDK

## Native Charts

Charts are now **native editable Word objects** (not PNG images):
- Double-click any chart to edit data in Excel
- Resizable without quality loss
- Word can apply document themes
- Matches manually-created corporate reports

### How It Works
1. Regex extracts `new Chart(...)` calls from `<script>` tags
2. Generates OOXML DrawingML chart XML (`c:chartSpace`) for each chart
3. Creates embedded Excel worksheets with source data (openpyxl)
4. Injects chart parts into the .docx ZIP with proper relationships
5. Supports: **bar**, **line**, **pie**, **doughnut**

### Corporate Color Palette
1. `#4E5B6F` - Dark blue-gray (primary)
2. `#007EEA` - Bright blue
3. `#898989` - Medium gray
4. `#D6ECFF` - Light blue
5. `#A7D6FF` - Sky blue
6. `#FFDF43` - Yellow accent

## Corporate Template

### Page Layout
- A4, margins 1.5cm L/R, 2.2cm top, 2.0cm bottom

### Fonts
| Style | Font | Size |
|-------|------|------|
| Body | Franklin Gothic Book | 10.5pt |
| Heading 1 | Franklin Gothic Book | 16pt bold #245375 |
| Heading 2 | Franklin Gothic Book | 13pt bold #245375 |
| Chart Title | Times New Roman | 10pt bold |
| Chart Source | Times New Roman | 9pt italic #202020 |

### Header
- Left: Report title | Right: Date (small caps, #666666, bottom border)

### Footer
- Separator line + Page number (left) + "Ekonomicke a Strategicke Analyzy" (center) + CSAS logo (right, floating)

### Table of Contents
- Auto-inserted after title, covers H2/H3 levels
- Update in Word: right-click -> "Update Field"

## Endpoints

- `GET /health` - Health check
- `POST /invocations` - Primary (Supervisor Agent)
- `POST /convert-to-docx` - Direct testing

## Output Location

```
/Volumes/agentbricks/volumes/agent_reports/
```

## Known Limitations

- SSE stream not parsed by agent (workaround: assume success)
- Chart types: bar, line, pie, doughnut only
- No JS callbacks/functions in chart configs
- TOC must be updated manually in Word

## Deployment

**App:** `agent-sector-report`
**URL:** `agent-sector-report-3863256616093854.14.azure.databricksapps.com`

### Service Principal Permissions
- `USE CATALOG` on `agentbricks`
- `USE SCHEMA` on `agentbricks.volumes`
- `READ/WRITE VOLUME` on `agentbricks.volumes.agent_reports`

## Dependencies

| Library | Purpose |
|---------|---------|
| fastapi | HTTP API |
| python-docx | Word document manipulation |
| htmldocx | HTML text/table conversion |
| beautifulsoup4 | HTML parsing |
| openpyxl | Embedded Excel for native charts |
| lxml | OOXML chart XML generation |
| databricks-sdk | UC Volume file upload |

## Project Structure

```
app/
  main.py                    # FastAPI endpoints
  template.docx              # Corporate template
  tools/
    html_to_docx_converter.py  # Chart extraction + native chart generation
docs/
  architecture.md
  agent_tool_contract.md
requirements.txt
app.yaml
start.sh
```
