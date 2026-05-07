import os
import re

import matplotlib.pyplot as plt
import pandas as pd

from sector_report_agent.app.config import CHART_VOLUME_PATH


def safe_file_name(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    return value.strip("_")


def create_bar_chart(
    records: list,
    x_col: str,
    y_col: str,
    title: str,
    file_name: str,
) -> str:
    os.makedirs(CHART_VOLUME_PATH, exist_ok=True)

    pdf = pd.DataFrame(records)

    if pdf.empty:
        raise ValueError("Cannot create chart from empty data.")

    if x_col not in pdf.columns:
        raise ValueError(f"Column {x_col} not found in chart data.")

    if y_col not in pdf.columns:
        raise ValueError(f"Column {y_col} not found in chart data.")

    output_path = f"{CHART_VOLUME_PATH}/{safe_file_name(file_name)}.png"

    plt.figure(figsize=(10, 6))
    plt.bar(pdf[x_col].astype(str), pdf[y_col])
    plt.title(title)
    plt.xlabel(x_col)
    plt.ylabel(y_col)
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    return output_path
