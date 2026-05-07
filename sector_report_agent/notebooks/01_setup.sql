CREATE CATALOG IF NOT EXISTS agentbricks;
CREATE SCHEMA IF NOT EXISTS agentbricks.test;

CREATE VOLUME IF NOT EXISTS agentbricks.test.agent_reports;

CREATE TABLE IF NOT EXISTS agentbricks.test.sector_report_state (
    report_id STRING,
    report_name STRING,
    analyst_user STRING,
    sector STRING,
    period STRING,
    section_name STRING,
    section_content STRING,
    chart_path STRING,
    report_docx_path STRING,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);