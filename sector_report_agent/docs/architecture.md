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
                          │ POST /invocations
                          │ (agent-to-agent message with JSON payload)
                          ▼
                 ┌─────────────────────────────────────┐
                 │  Sector Report App (This FastAPI App)│
                 │                                     │
                 │  ┌───────────────────────────────┐  │
                 │  │ 0. Message Parsing            │  │
                 │  │    - Extract JSON from agent  │  │
                 │  │      message content field    │  │
                 │  └───────────────────────────────┘  │
                 │                 │                    │
                 │                 ▼                    │
                 │  ┌───────────────────────────────┐  │
                 │  │ 1. Regex Chart Extraction     │  │
                 │  │    - Parse new Chart(...) calls│  │
                 │  │    - Extract type, labels,    │  │
                 │  │      datasets, colors, title  │  │
                 │  └───────────────────────────────┘  │
                 │                 │                    │
                 │                 ▼                    │
                 │  ┌───────────────────────────────┐  │
                 │  │ 2. Matplotlib Rendering       │  │
                 │  │    - Chart config → PNG bytes │  │
                 │  │    - bar, line, pie, doughnut │  │
                 │  └───────────────────────────────┘  │
                 │                 │                    │
                 │                 ▼                    │
                 │  ┌───────────────────────────────┐  │
                 │  │ 3. DOCX Assembly (hybrid)     │  │
                 │  │    - htmldocx: text + tables  │  │
                 │  │    - python-docx: add_picture │  │
                 │  │      for chart images         │  │
                 │  └───────────────────────────────┘  │
                 │                 │                    │
                 │                 ▼                    │
                 │  ┌───────────────────────────────┐  │
                 │  │ 4. Databricks SDK Upload      │  │
                 │  │    - files.upload() to Volume │  │
                 │  └───────────────────────────────┘  │
                 │                 │                    │
                 │                 ▼                    │
                 │  ┌───────────────────────────────┐  │
                 │  │ 5. SSE Stream Response        │  │
                 │  │    - Anthropic-style events   │  │
                 │  │    - (see Known Issue below)  │  │
                 │  └───────────────────────────────┘  │
                 └─────────────────────────────────────┘
                          │
                          │ Saved .docx file
                          ▼
                 ┌─────────────────────┐
                 │   UC Volume         │
                 │   /Volumes/agent-   │
                 │   bricks/volumes/   │
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
3. **Supervisor Agent** calls this app via `POST /invocations` with a message containing JSON: `{"filename": "...", "html_content": "..."}`.
4. **Sector Report App** (FastAPI) processes the request:
   - **Step 0 - Message Parsing**: Extracts the JSON payload from the agent message's `content` field (supports direct JSON, brace-matching, and raw HTML detection).
   - **Step 1 - Chart Extraction**: Regex finds `new Chart(document.getElementById('id'), {...})` calls and parses chart type, labels, data arrays, colors, and title.
   - **Step 2 - Matplotlib Rendering**: Each extracted chart config is rendered to PNG bytes using matplotlib (supports bar, line, pie, doughnut charts).
   - **Step 3 - DOCX Assembly**: Canvas elements are replaced with text placeholders. The cleaned HTML (text + tables) is converted via `htmldocx`. Then placeholder paragraphs are found and replaced with chart images via `python-docx`'s `add_picture()`.
   - **Step 4 - Volume Upload**: The DOCX is serialized to bytes and uploaded to the UC Volume using `WorkspaceClient().files.upload()`.
   - **Step 5 - SSE Response**: Returns an Anthropic-style SSE stream with the success message and file path.
5. **UC Volume** stores the Word document at `/Volumes/agentbricks/volumes/agent_reports/<filename>.docx`.
6. **Supervisor Agent** reports success to the user (see Known Issue below for response handling).

## Components

| Component | Role |
|-----------|------|
| Supervisor Agent | Orchestrates report generation; produces HTML + Chart.js |
| Genie Space | Provides data access and query capabilities |
| `/invocations` endpoint | Receives agent messages, parses JSON, triggers conversion |
| `/convert-to-docx` endpoint | Direct testing endpoint (bypasses agent message format) |
| Regex Parser | Extracts Chart.js configurations from script tags |
| Matplotlib | Renders charts server-side as PNG images |
| htmldocx | Converts HTML text and tables to DOCX format |
| python-docx | Inserts chart images and manipulates Word document |
| Databricks SDK | Uploads final .docx to UC Volume via Files API |

## Design Decisions

### Why not Playwright/headless browser?
Databricks Apps containers lack the system libraries (libnspr4, libnss3, etc.) required by Chromium. Since `apt-get install` isn't available, a pure-Python solution (matplotlib) is used instead.

### Why hybrid DOCX assembly?
`htmldocx` cannot handle `<img src="data:image/png;base64,...">` tags (it tries to open the data URI as a file path, resulting in "File name too long" error). Instead, we use text placeholders during HTML conversion and post-process the DOCX to insert images with `python-docx`.

### Why Databricks SDK for file writes?
UC Volumes aren't available as a FUSE filesystem in Databricks Apps containers. The SDK's `files.upload()` method writes to volumes over the API.

### Why `/invocations` endpoint?
The Databricks Supervisor Agent framework calls sub-agent apps via `POST /invocations` using a chat message format (`{"input": [{"role": "user", "content": "..."}], "stream": true}`). The app must parse the JSON payload from within the message content field.

### Why Anthropic-style SSE format?
The Supervisor Agent expects responses as Server-Sent Events with Anthropic message format (message_start → content_block_start → content_block_delta → content_block_stop → message_delta → message_stop).

## Known Issue: SSE Stream Not Parsed by Agent

**Problem:** The Databricks Supervisor Agent infrastructure currently cannot parse the SSE stream from this app. The conversion completes successfully (verified via app logs and file checks), but the agent reports "Tool returned no content."

**Root cause candidates:**
- FastAPI `StreamingResponse` buffering behavior
- Possible incompatibility between the agent infrastructure's SSE parser and the response format
- Potential proxy/gateway buffering between the app and the agent framework

**Workaround (current solution):** The Supervisor Agent's system prompt includes instructions to assume success when the tool returns no content, and to construct the file path from the filename it sent: `/Volumes/agentbricks/volumes/agent_reports/{filename}`.

**Impact:** None on functionality. The DOCX is always saved correctly. Only the confirmation message back to the agent is lost.

## Security Considerations

- **Filename sanitization**: All filenames are stripped of path traversal characters before writing.
- **Volume isolation**: The app only writes to a single, pre-configured volume path.
- **Input validation**: The endpoint validates that filenames end with `.docx` and rejects malformed requests.
- **No code execution**: Charts are rendered by parsing data from HTML, not by executing arbitrary JavaScript.
- **Service principal**: App uses a dedicated SP with minimal permissions (volume read/write only).
