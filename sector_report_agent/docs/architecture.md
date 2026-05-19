# Architecture

## High-Level Flow

```
User -> Supervisor Agent -> Genie Space (data)
                        -> HTML + Chart.js generation
                        -> POST /invocations
                        -> Sector Report App:
                             1. Load corporate template
                             2. Extract Chart.js configs (regex)
                             3. Generate native Word charts (OOXML)
                             4. Create embedded Excel data (openpyxl)
                             5. Convert HTML text/tables (htmldocx)
                             6. Insert TOC ("Obsah")
                             7. Apply corporate styling
                             8. Inject chart parts into ZIP
                             9. Upload to UC Volume
                        -> /Volumes/agentbricks/volumes/agent_reports/*.docx
```

## DOCX Assembly Pipeline

```
template.docx (loaded)
       |
       v
Replace header placeholders
  {{REPORT_TITLE}} -> h1 text
  {{REPORT_DATE}}  -> "May 2026"
       |
       v
Convert HTML via htmldocx
  Text, tables, lists, headings
  Canvas -> text placeholders
       |
       v
Insert Table of Contents
  "Obsah" heading (H1)
  TOC field (levels 2-3)
  Page break
       |
       v
Replace chart placeholders
  For each canvas_id:
  - Insert chart title (bold, TNR 10pt)
  - Insert inline chart drawing reference (rId)
  - Insert source citation (italic, TNR 9pt)
       |
       v
Apply corporate styling
  Franklin Gothic Book on all runs
       |
       v
Save to bytes -> ZIP post-processing:
  - Add [Content_Types].xml entries for chart/xlsx parts
  - Add document.xml.rels for chart relationships
  - Inject word/charts/chartN.xml (DrawingML)
  - Inject word/embeddings/Microsoft_Excel_WorksheetN.xlsx
  - Add chart rels (chart -> embedded xlsx)
       |
       v
Upload to UC Volume via SDK
```

## Native Chart Architecture

Each chart in the document consists of:

1. **Inline drawing reference** in `word/document.xml`
   - `w:drawing > wp:inline > a:graphic > a:graphicData > c:chart r:id="rIdN"`

2. **Chart XML** at `word/charts/chartN.xml`
   - `c:chartSpace > c:chart > c:plotArea > c:barChart/c:lineChart/c:pieChart`
   - Contains: series data (cached), axis definitions, colors, title, legend

3. **Embedded Excel** at `word/embeddings/Microsoft_Excel_WorksheetN.xlsx`
   - Contains the source data that Word uses when editing the chart
   - Linked from chart via `c:externalData r:id="rId1"`

4. **Relationships**:
   - `word/_rels/document.xml.rels`: document -> chart
   - `word/charts/_rels/chartN.xml.rels`: chart -> embedded xlsx

## Design Decisions

### Why native Word charts instead of matplotlib PNGs?
- **Editability**: Users can modify data directly in Word
- **Professional**: Matches manually-created corporate documents
- **Scalability**: Vector graphics, no pixelation on resize
- **Smaller files**: Chart XML + data is smaller than high-res PNGs

### Why two-pass ZIP approach?
python-docx cannot directly create chart parts. The approach:
1. Build document normally with python-docx (text, tables, drawing references)
2. Save to bytes, then manipulate the ZIP to inject chart XML and Excel files
This avoids monkey-patching python-docx internals.

### Why openpyxl for embedded Excel?
Word charts require an embedded `.xlsx` as the data source for editing.
openpyxl creates valid Excel files that Word can open.

### Why regex for Chart.js extraction?
The HTML is never rendered in a browser. Regex reliably extracts:
- Chart type, labels, data arrays, colors, titles
- Two patterns: direct `getElementById` and variable-based
- Brace matching scopes each chart config to prevent bleed-over

### Why a DOCX template?
Corporate documents require specific fonts, styled headers/footers with logos,
page margins, and consistent branding that htmldocx cannot produce alone.

### Why TOC levels 2-3 only?
The title (H1) and "Obsah" itself (H1) should not appear in the table of contents.

## Components

| Component | Role |
|-----------|------|
| Supervisor Agent | Produces HTML + Chart.js |
| Genie Space | Data access |
| template.docx | Corporate styling |
| Regex Parser | Extracts Chart.js configs |
| _create_chart_xml() | Generates DrawingML chart XML |
| _create_chart_xlsx() | Generates embedded Excel data |
| _inject_charts_into_docx() | ZIP post-processing |
| htmldocx | HTML text/table conversion |
| python-docx | Document manipulation |
| Databricks SDK | Volume upload |

## Security

- Filename sanitization (no path traversal)
- Single pre-configured volume path
- No code execution (regex parsing only)
- Dedicated service principal with minimal permissions
