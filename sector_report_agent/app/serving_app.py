import uuid
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field
from pyspark.sql import SparkSession

from sector_report_agent.app.tools.chart_tool import create_bar_chart
from sector_report_agent.app.tools.report_docx_tool import generate_docx_report
from sector_report_agent.app.tools.report_state_tool import save_report_state


app = FastAPI(title="Sector Report Generator")

spark = SparkSession.builder.getOrCreate()


class ReportRequest(BaseModel):
    analyst_user: str = Field(default="unknown")
    sector: str
    period: str
    executive_summary: str
    market_overview: str
    key_trends: str
    financial_development: str
    risks: str
    conclusion: str
    chart_paths: Optional[list] = None


class ChartRequest(BaseModel):
    records: list[dict]
    x_col: str
    y_col: str
    title: str
    file_name: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate-report")
def generate_report(request: ReportRequest):
    report_id = str(uuid.uuid4())
    report_name = f"{request.sector} Sector Analysis {request.period}"

    sections = {
        "Executive Summary": request.executive_summary,
        "Market Overview": request.market_overview,
        "Key Trends": request.key_trends,
        "Financial Development": request.financial_development,
        "Risks": request.risks,
        "Conclusion": request.conclusion,
    }

    chart_paths = request.chart_paths or []

    report_docx_path = generate_docx_report(
        report_name=report_name,
        sector=request.sector,
        period=request.period,
        sections=sections,
        chart_paths=chart_paths,
    )

    save_report_state(
        spark=spark,
        report_id=report_id,
        report_name=report_name,
        analyst_user=request.analyst_user,
        sector=request.sector,
        period=request.period,
        sections=sections,
        chart_paths=chart_paths,
        report_docx_path=report_docx_path,
    )

    return {
        "report_id": report_id,
        "report_docx_path": report_docx_path,
    }


@app.post("/generate-chart")
def generate_chart(request: ChartRequest):
    chart_path = create_bar_chart(
        records=request.records,
        x_col=request.x_col,
        y_col=request.y_col,
        title=request.title,
        file_name=request.file_name,
    )

    return {
        "chart_path": chart_path,
    }
