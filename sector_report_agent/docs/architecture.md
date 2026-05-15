# Architecture

## High-Level Overview

This application is part of a Supervisor Agent workflow that generates and persists sector analysis reports.

```
┌──────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   User   │────▶│  Supervisor Agent    │────▶│   Genie Space   │
└──────────┘     └─────────────────────┘     └─────────────────┘
                          │                           │
                          │  Orchestrates             │ Returns data
                          │                           │
                          ▼                           ▼
                 ┌─────────────────────┐     ┌─────────────────┐
                 │  HTML Generation    │◀────│  Chart Creation  │
                 └─────────────────────┘     └─────────────────┘
                          │
                          │ POST /save-html-report
                          ▼
                 ┌─────────────────────┐
                 │  Sector Report App  │
                 │  (This FastAPI App) │
                 └─────────────────────┘
                          │
                          │ Write file
                          ▼
                 ┌─────────────────────┐
                 │   UC Volume         │
                 │   /Volumes/agent-   │
                 │   bricks/test/      │
                 │   agent_reports/    │
                 └─────────────────────┘
```

## Flow Description

1. **User** triggers the Supervisor Agent with a request (e.g., "Generate automotive sector report").
2. **Supervisor Agent** orchestrates the workflow:
   - Queries the **Genie Space** for relevant data and metrics.
   - Generates charts and visualizations.
   - Assembles the final HTML report content.
3. **Supervisor Agent** calls the `save_html_report` tool (this app's `/save-html-report` endpoint).
4. **Sector Report App** (FastAPI):
   - Validates and sanitizes the filename.
   - Writes the HTML content to the Unity Catalog Volume.
   - Returns confirmation with the saved file path.
5. **UC Volume** stores the report at `/Volumes/agentbricks/test/agent_reports/<filename>.html`.

## Components

| Component | Role |
|-----------|------|
| Supervisor Agent | Orchestrates the full report generation pipeline |
| Genie Space | Provides data access and query capabilities |
| HTML Generation | Assembles data + charts into a complete HTML report |
| Sector Report App | Persists the generated HTML to durable storage |
| UC Volume | Unity Catalog Volume for report file storage |

## Security Considerations

- **Filename sanitization**: All filenames are stripped of path traversal characters before writing.
- **Volume isolation**: The app only writes to a single, pre-configured volume path.
- **Input validation**: The endpoint validates that filenames end with `.html` and rejects malformed requests.
