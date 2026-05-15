# Architecture

## High-Level Overview

This application is part of a Supervisor Agent workflow that generates sector analysis reports with charts and converts them to Word documents.

```
┌──────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   User   │────▶│  Supervisor Agent    │────▶│   Genie Space   │
└──────────┘     └─────────────────────┘     └─────────────────┘
                          │                           │
                          │  Orchestrates             │ Returns data
                          │                           │
                          ▼                           ▼
                 ┌─────────────────────┐     ┌─────────────────┐
                 │  HTML + Chart.js    │◀────│  Data Analysis   │
                 │  Report Generation  │     │  & Formatting    │
                 └─────────────────────┘     └─────────────────┘
                          │
                          │ POST /convert-to-docx
                          │ (sends full HTML with JS)
                          ▼
                 ┌─────────────────────────────────────┐
                 │  Sector Report App (This FastAPI App)│
                 │                                     │
                 │  ┌───────────────────────────────┐  │
                 │  │ 1. Playwright (headless Chrome)│  │
                 │  │    - Loads HTML                │  │
                 │  │    - Executes Chart.js         │  │
                 │  │    - Canvas → PNG base64       │  │
                 │  └───────────────────────────────┘  │
                 │                 │                    │
                 │                 ▼                    │
                 │  ┌───────────────────────────────┐  │
                 │  │ 2. htmldocx + python-docx     │  │
                 │  │    - Rendered HTML → DOCX     │  │
                 │  │    - Charts as embedded images │  │
                 │  └───────────────────────────────┘  │
                 └─────────────────────────────────────┘
                          │
                          │ Write .docx file
                          ▼
                 ┌─────────────────────┐
                 │   UC Volume         │
                 │   /Volumes/agent-   │
                 │   bricks/test/      │
                 │   agent_reports/    │
                 │                     │
                 │   *.docx files      │
                 └─────────────────────┘
```

## Flow Description

1. **User** triggers the Supervisor Agent with a request (e.g., "Generate automotive sector report").
2. **Supervisor Agent** orchestrates the workflow:
   - Queries the **Genie Space** for relevant data and metrics.
   - Generates a complete HTML report with Chart.js visualizations.
3. **Supervisor Agent** calls the `convert_html_to_docx` tool with the full HTML content.
4. **Sector Report App** (FastAPI):
   - Detects JavaScript in the HTML.
   - Renders the page in headless Chromium (Playwright).
   - Converts `<canvas>` chart elements to base64 PNG images.
   - Converts the rendered HTML (with inline images) to DOCX via `htmldocx`.
   - Saves the .docx file to the Unity Catalog Volume.
   - Returns confirmation with the saved file path.
5. **UC Volume** stores the Word document at `/Volumes/agentbricks/test/agent_reports/<filename>.docx`.

## Components

| Component | Role |
|-----------|------|
| Supervisor Agent | Orchestrates report generation; produces HTML + Chart.js |
| Genie Space | Provides data access and query capabilities |
| Playwright | Renders JS charts in headless Chromium |
| htmldocx | Converts rendered HTML to DOCX format |
| python-docx | Word document manipulation and image embedding |
| UC Volume | Unity Catalog Volume for report file storage |

## Security Considerations

- **Filename sanitization**: All filenames are stripped of path traversal characters before writing.
- **Volume isolation**: The app only writes to a single, pre-configured volume path.
- **Input validation**: The endpoint validates that filenames end with `.docx` and rejects malformed requests.
- **Browser isolation**: Playwright runs in headless mode with no persistent state between requests.
- **Network access**: The headless browser needs CDN access to load Chart.js from `cdn.jsdelivr.net`.
