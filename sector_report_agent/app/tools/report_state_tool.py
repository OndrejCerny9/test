from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    TimestampType,
)

from sector_report_agent.app.config import REPORT_STATE_TABLE


REPORT_STATE_SCHEMA = StructType(
    [
        StructField("report_id", StringType(), False),
        StructField("report_name", StringType(), False),
        StructField("analyst_user", StringType(), True),
        StructField("sector", StringType(), True),
        StructField("period", StringType(), True),
        StructField("section_name", StringType(), True),
        StructField("section_content", StringType(), True),
        StructField("chart_path", StringType(), True),
        StructField("report_docx_path", StringType(), True),
        StructField("created_at", TimestampType(), True),
        StructField("updated_at", TimestampType(), True),
    ]
)


def save_report_state(
    spark: SparkSession,
    report_id: str,
    report_name: str,
    analyst_user: str,
    sector: str,
    period: str,
    sections: dict,
    chart_paths: list,
    report_docx_path: str,
) -> None:
    now = datetime.now()

    rows = []

    for section_name, section_content in sections.items():
        rows.append(
            {
                "report_id": report_id,
                "report_name": report_name,
                "analyst_user": analyst_user,
                "sector": sector,
                "period": period,
                "section_name": section_name,
                "section_content": section_content,
                "chart_path": None,
                "report_docx_path": report_docx_path,
                "created_at": now,
                "updated_at": now,
            }
        )

    for chart_path in chart_paths:
        rows.append(
            {
                "report_id": report_id,
                "report_name": report_name,
                "analyst_user": analyst_user,
                "sector": sector,
                "period": period,
                "section_name": "Charts",
                "section_content": None,
                "chart_path": chart_path,
                "report_docx_path": report_docx_path,
                "created_at": now,
                "updated_at": now,
            }
        )

    (
        spark.createDataFrame(rows, schema=REPORT_STATE_SCHEMA)
        .write
        .mode("append")
        .saveAsTable(REPORT_STATE_TABLE)
    )