# Sector Report Agent

Architecture:

Supervisor Agent
- Genie Space: `sector_analysis_genie_space`
- Agent Endpoint: `Sector Report Generator`

The Genie Space performs analytical work over:

`agentbricks.sector_data_bronze`

The Agent Endpoint creates:
- Word reports
- PNG charts
- report state records

Output path:

`/Volumes/agentbricks/test/agent_reports`

## Setup

Run:

`notebooks/01_setup.sql`

Install requirements:

`pip install -r requirements.txt`

Run local app:

`uvicorn app.serving_app:app --host 0.0.0.0 --port 8000`

## Supervisor Agent setup

Add sub-agent 1:

Type: Genie Space  
Source: sector_analysis_genie_space  
Agent Name: sector_analyst  

Add sub-agent 2:

Type: Agent Endpoint  
Source: deployed report generator endpoint  
Agent Name: report_generator  