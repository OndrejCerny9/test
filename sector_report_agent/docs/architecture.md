# Architecture

## High-Level Overview

This application is part of a Supervisor Agent workflow that generates sector analysis reports with charts and converts them to corporate-styled Word documents.

```
+----------+     +---------------------+     +-----------------+
|   User   |---->|  Supervisor Agent    |---->|   Genie Space   |
+----------+     +---------------------+     +-----------------+
                          |                           |
                          |  Orchestrates             | Returns data
                          |                           |
                          v                           v
                 +---------------------+     +-----------------+
                 |  HTML + Chart.js    |<----|  Data Analysis   |
                 |  Report Generation  |     |  & Formatting    |
                 +---------------------+     +-----------------+
                          |
                          | POST /invocations
                          | (agent-to-agent message with JSON payload)
                          v
                 +-------------------------------------+
                 |  Sector Report App (This FastAPI App)|
                 |                                     |
                 |  +-------------------------------+  |
                 |  | 0. Message Parsing            |  |
                 |  |    - Extract JSON from agent  |  |
                 |  |      message content field    |  |
                 |  +-------------------------------+  |
                 |                 |                    |
                 |                 v                    |
                 |  +-------------------------------+  |
                 |  | 1. Load Corporate Template    |  |
                 |  |    - template.docx with       |  |
                 |  |      styles, header/footer    |  |
                 |  +-------------------------------+  |
                 |                 |                    |
                 |                 v                    |
                 |  +-------------------------------+  |
                 |  | 2. Regex Chart Extraction     |  |
                 |  |    - Parse new Chart(...) calls|  |
                 |  |    - Extract type, labels,    |  |
                 |  |      datasets, colors, title  |  |
                 |  +-------------------------------+  |
                 |                 |                    |
                 |                 v                    |
                 |  +-------------------------------+  |
                 |  | 3. Matplotlib Rendering       |  |
                 |  |    - Chart config -> PNG bytes|  |
                 |  |    - Corporate color palette  |  |
                 |  |    - bar, line, pie, doughnut |  |
                 |  +-------------------------------+  |
                 |                 |                    |
                 |                 v                    |
                 |  +-------------------------------+  |
                 |  | 4. DOCX Assembly              |  |
                 |  |    - htmldocx: text + tables  |  |
                 |  |    - python-docx: charts      |  |
                 |  |    - Insert TOC ("Obsah")     |  |
                 |  |    - Replace header/footer    |  |
                 |  |      placeholders             |  |
                 |  |    - Apply corporate styling  |  |
                 |  +-------------------------------+  |
                 |                 |                    |
                 |                 v                    |
                 |  +-------------------------------+  |
                 |  | 5. Databricks SDK Upload      |  |
                 |  |    - files.upload() to Volume |  |
                 |  +-------------------------------+  |
                 |                 |                    |
                 |                 v                    |
                 |  +-------------------------------+  |
                 |  | 6. SSE Stream Response        |  |
                 |  |    - Anthropic-style events   |  |
                 |  |    - (see Known Issue below)  |  |
                 |  +-------------------------------+  |
                 +-------------------------------------+
                          |
                          | Saved .docx file
                          v
                 +---------------------+
                 |   UC Volume         |
                 |   /Volumes/agent-   |
                 |   bricks/volumes/   |
                 |   agent_reports/    |
                 |                     |
                 |   *.docx files      |
                 +---------------------+
```

## DOCX Assembly Pipeline (Step 4 in Detail)

The DOCX assembly is the core of the converter. It proceeds as follows:

```
template.docx (loaded)
       |
       v
+-- Replace header placeholders --+
|   {{REPORT_TITLE}} -> h1 text   |
|   {{REPORT_DATE}}  -> "May 2026"|
+---------------------------------+
       |
       v
+-- Convert HTML via htmldocx ----+
|   Text, tables, lists, headings |
|   Canvas -> text placeholders   |
+---------------------------------+
       |
       v
+-- Insert Table of Contents -----+
|   "Obsah" heading (H1)          |
|   TOC field (levels 2-3)        |
|   Page break                    |
+---------------------------------+
       |
       v
+-- Replace chart placeholders ---+
|   For each canvas_id:           |
|   - Insert chart title (bold)   |
|   - Insert PNG image (16cm wide)|
|   - Insert source citation      |
+---------------------------------+
       |
       v
+-- Apply corporate styling ------+
|   Set Franklin Gothic Book on   |
|   all runs where font.name=None |
|   Set table cell fonts/sizes    |
+---------------------------------+
       |
       v
     Final Document
```

## Components

| Component | Role |
|-----------|------|
| Supervisor Agent | Orchestrates report generation; produces HTML + Chart.js |
| Genie Space | Provides data access and query capabilities |
| `/invocations` endpoint | Receives agent messages, parses JSON, triggers conversion |
| `/convert-to-docx` endpoint | Direct testing endpoint (bypasses agent message format) |
| `template.docx` | Corporate template with styles, header/footer, page setup |
| Regex Parser | Extracts Chart.js configurations from script tags |
| Matplotlib | Renders charts server-side as PNG images |
| htmldocx | Converts HTML text and tables to DOCX format |
| python-docx | Inserts chart images, TOC field, manipulates Word document |
| Databricks SDK | Uploads final .docx to UC Volume via Files API |

## Design Decisions

### Why a DOCX template?
The corporate document requires specific fonts (Franklin Gothic Book), styled headers/footers with logos, page margins, and consistent branding. A pre-built template.docx ensures these elements are preserved across all generated reports, even though `htmldocx` doesn't natively support template styles.

### Why post-process fonts?
`htmldocx` creates runs with `font.name=None`, which causes Word to fall back to Calibri. The `_apply_corporate_styling()` function iterates all paragraphs/tables and explicitly sets Franklin Gothic Book on any run where the font wasn't set.

### Why a floating/anchored logo?
The footer logo must be right-aligned without affecting the centered text. Using an inline image would push the text left. An anchored (floating) image with `wp:anchor` positioning allows the logo to sit independently at the right margin while the text remains centered.

### Why two footer paragraphs?
A single paragraph with a top border would have the border line intersecting with the floating logo. Separating the line into its own minimal-height paragraph with a bottom border ensures the line and logo don't interfere.

### Why TOC with levels 2-3?
The title (H1) and "Obsah" itself (H1) should not appear in the table of contents. Using `\o "2-3"` in the TOC field code limits entries to Heading 2 (main sections) and Heading 3 (subsections).

### Why not Playwright/headless browser?
Databricks Apps containers lack the system libraries (libnspr4, libnss3, etc.) required by Chromium. A pure-Python solution (matplotlib) is used instead.

### Why hybrid DOCX assembly?
`htmldocx` cannot handle `<img src="data:image/png;base64,...">` tags. Instead, we use text placeholders during HTML conversion and post-process the DOCX to insert images with `python-docx`.

### Why Databricks SDK for file writes?
UC Volumes are not available as a FUSE filesystem in Databricks Apps containers. The SDK's `files.upload()` method writes to volumes over the API.

## Known Issue: SSE Stream Not Parsed by Agent

**Problem:** The Supervisor Agent infrastructure currently cannot parse the SSE stream from this app. The conversion completes successfully, but the agent reports "Tool returned no content."

**Workaround:** The Supervisor Agent's system prompt includes instructions to assume success when the tool returns no content, and to construct the file path from the filename it sent.

**Impact:** None on functionality. The DOCX is always saved correctly.

## Security Considerations

- **Filename sanitization**: All filenames are stripped of path traversal characters before writing.
- **Volume isolation**: The app only writes to a single, pre-configured volume path.
- **Input validation**: The endpoint validates that filenames end with `.docx`.
- **No code execution**: Charts are rendered by parsing data from HTML, not by executing arbitrary JavaScript.
- **Service principal**: App uses a dedicated SP with minimal permissions (volume read/write only).
