"""
HTML to DOCX Converter Tool

Converts HTML report content (including Chart.js configurations) to a Word
document (.docx) and saves it to a Unity Catalog Volume.

Flow:
1. Parse HTML to find Chart.js <script> blocks
2. Extract chart configuration (labels, datasets, chart type)
3. Render charts as PNG images using matplotlib
4. Replace <canvas> placeholders with rendered chart images
5. Convert the resulting HTML (with inline base64 images) to DOCX via htmldocx
6. Save the .docx file to the configured UC Volume via Databricks SDK
"""

import os
import io
import re
import json
import base64
import logging
from bs4 import BeautifulSoup
from docx import Document
from htmldocx import HtmlToDocx
from databricks.sdk import WorkspaceClient
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_VOLUME_PATH = "/Volumes/agentbricks/volumes/agent_reports"


def get_volume_path() -> str:
    """Get the configured volume path from environment or use default."""
    return os.environ.get("REPORT_VOLUME_PATH", DEFAULT_VOLUME_PATH)


def _extract_chart_configs(html_content: str) -> list:
    """
    Extract Chart.js configurations from <script> blocks in the HTML.
    Uses regex to find chart type, labels, data arrays, and labels.
    """
    charts = []

    # Find all canvas IDs referenced in new Chart(...) calls
    pattern = r'new\s+Chart\s*\(\s*document\.getElementById\s*\(\s*[\x27"]([^\x27"]+)[\x27"]\s*\)'
    for match in re.finditer(pattern, html_content):
        canvas_id = match.group(1)
        start_pos = match.start()

        # Find the enclosing script block content around this Chart call
        # Look for the config object that follows
        rest = html_content[match.end():]

        # Extract chart type
        type_match = re.search(r'type\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:500])
        chart_type = type_match.group(1) if type_match else "bar"

        # Extract labels array
        labels_match = re.search(r'labels\s*:\s*\[([^\]]+)\]', rest[:2000])
        labels = []
        if labels_match:
            labels = [l.strip().strip("\x27\"") for l in labels_match.group(1).split(",")]

        # Extract data arrays and dataset labels
        datasets = []
        data_arrays = re.findall(r'data\s*:\s*\[([\d.,\s]+)\]', rest[:5000])
        ds_labels = re.findall(r'label\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:5000])
        bg_colors = re.findall(r'backgroundColor\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:5000])

        for i, data_str in enumerate(data_arrays):
            try:
                data_vals = [float(x.strip()) for x in data_str.split(",") if x.strip()]
                dataset = {"data": data_vals}
                if i < len(ds_labels):
                    dataset["label"] = ds_labels[i]
                if i < len(bg_colors):
                    dataset["backgroundColor"] = bg_colors[i]
                datasets.append(dataset)
            except ValueError:
                continue

        # Extract title
        title_text = None
        title_match = re.search(r'text\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:5000])
        if title_match:
            title_text = title_match.group(1)

        if labels and datasets:
            config = {
                "type": chart_type,
                "data": {"labels": labels, "datasets": datasets},
                "options": {"plugins": {"title": {"display": bool(title_text), "text": title_text}}}
            }
            charts.append({"canvas_id": canvas_id, "config": config})
            logger.info(f"Extracted chart config for canvas: {canvas_id}")

    return charts


def _parse_color(color_str) -> tuple:
    """Parse rgba/rgb/hex color string to matplotlib-compatible format."""
    if not isinstance(color_str, str):
        return '#667eea'

    color_str = color_str.strip()

    rgba_match = re.match(r'rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)', color_str)
    if rgba_match:
        r = int(float(rgba_match.group(1)))
        g = int(float(rgba_match.group(2)))
        b = int(float(rgba_match.group(3)))
        a = float(rgba_match.group(4)) if rgba_match.group(4) else 1.0
        return (r/255, g/255, b/255, a)

    if color_str.startswith('#'):
        return color_str

    return '#667eea'


def _render_chart_to_base64(config: dict) -> str:
    """
    Render a chart configuration to a PNG image using matplotlib.
    Returns a base64-encoded PNG string.
    """
    chart_type = config.get("type", "bar")
    data = config.get("data", {})
    labels = data.get("labels", [])
    datasets = data.get("datasets", [])
    options = config.get("options", {})

    default_colors = [
        '#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe',
        '#00f2fe', '#43e97b', '#fa709a', '#fee140', '#a18cd1'
    ]

    fig, ax = plt.subplots(figsize=(10, 5))

    if chart_type == "bar":
        x = np.arange(len(labels))
        n_datasets = max(len(datasets), 1)
        width = 0.8 / n_datasets

        for i, ds in enumerate(datasets):
            offset = (i - n_datasets / 2 + 0.5) * width
            color = _parse_color(ds.get("backgroundColor", default_colors[i % len(default_colors)]))
            ax.bar(x + offset, ds.get("data", []), width,
                   label=ds.get("label", ""), color=color)

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=11, fontweight='bold')

    elif chart_type == "line":
        for i, ds in enumerate(datasets):
            color = _parse_color(ds.get("backgroundColor", default_colors[i % len(default_colors)]))
            ax.plot(labels, ds.get("data", []), marker='o', linewidth=2.5,
                    label=ds.get("label", ""), color=color, markersize=6)

    elif chart_type in ("pie", "doughnut"):
        if datasets:
            ds = datasets[0]
            colors = [_parse_color(default_colors[i % len(default_colors)]) for i in range(len(labels))]
            wedgeprops = {"width": 0.4} if chart_type == "doughnut" else {}
            ax.pie(ds.get("data", []), labels=labels, colors=colors,
                   autopct='%1.1f%%', wedgeprops=wedgeprops)
            ax.set_aspect('equal')

    else:
        # Fallback: bar
        x = np.arange(len(labels))
        if datasets:
            color = _parse_color(datasets[0].get("backgroundColor", default_colors[0]))
            ax.bar(x, datasets[0].get("data", []), color=color,
                   label=datasets[0].get("label", ""))
            ax.set_xticks(x)
            ax.set_xticklabels(labels, fontsize=11)

    # Title
    plugins = options.get("plugins", {})
    title_cfg = plugins.get("title", {})
    if title_cfg.get("display") and title_cfg.get("text"):
        ax.set_title(title_cfg["text"], fontsize=14, fontweight='bold', pad=15)

    # Legend
    if chart_type not in ("pie", "doughnut"):
        if any(ds.get("label") for ds in datasets):
            ax.legend(loc='upper left', fontsize=10)

    # Style
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()

    # Render to base64 PNG
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode('utf-8')


def _html_has_scripts(html_content: str) -> bool:
    """Check if HTML contains script tags."""
    soup = BeautifulSoup(html_content, "html.parser")
    return bool(soup.find_all("script"))


def _render_charts_into_html(html_content: str) -> str:
    """
    Extract Chart.js configs, render with matplotlib, and replace canvas
    elements with base64 images.
    """
    charts = _extract_chart_configs(html_content)
    soup = BeautifulSoup(html_content, "html.parser")

    for chart_info in charts:
        canvas_id = chart_info["canvas_id"]
        config = chart_info["config"]

        try:
            img_base64 = _render_chart_to_base64(config)

            canvas = soup.find("canvas", {"id": canvas_id})
            if canvas:
                img_tag = soup.new_tag("img")
                img_tag["src"] = f"data:image/png;base64,{img_base64}"
                img_tag["style"] = "max-width: 100%; display: block; margin: 10px auto;"

                parent = canvas.parent
                if parent and parent.name == "div":
                    parent.replace_with(img_tag)
                else:
                    canvas.replace_with(img_tag)

                logger.info(f"Rendered chart for canvas: {canvas_id}")
        except Exception as e:
            logger.warning(f"Failed to render chart {canvas_id}: {e}")

    # Remove script and style tags
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    body = soup.find("body")
    return str(body) if body else str(soup)


def _build_docx_from_html(rendered_html: str) -> Document:
    """Build a DOCX document from rendered HTML."""
    doc = Document()
    parser = HtmlToDocx()
    parser.add_html_to_document(rendered_html, doc)
    return doc


def _save_to_volume(doc: Document, volume_path: str, filename: str) -> str:
    """Save a DOCX document to a UC Volume using the Databricks SDK."""
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    full_path = f"{volume_path}/{filename}"
    w = WorkspaceClient()
    w.files.upload(full_path, buffer, overwrite=True)

    return full_path


def convert_html_to_docx(filename: str, html_content: str) -> dict:
    """
    Convert HTML content (including Chart.js configurations) to a Word document
    and save to the configured Unity Catalog Volume.
    """
    volume_path = get_volume_path()
    logger.info(f"Target volume path: {volume_path}")

    try:
        if _html_has_scripts(html_content):
            logger.info("HTML contains scripts - rendering charts with matplotlib")
            rendered_html = _render_charts_into_html(html_content)
        else:
            logger.info("HTML is static - converting directly")
            soup = BeautifulSoup(html_content, "html.parser")
            body = soup.find("body")
            rendered_html = str(body) if body else html_content

        doc = _build_docx_from_html(rendered_html)

    except Exception as e:
        logger.error(f"HTML to DOCX conversion failed: {e}")
        raise ValueError(f"HTML to DOCX conversion failed: {e}") from e

    try:
        full_path = _save_to_volume(doc, volume_path, filename)
        logger.info(f"DOCX report saved successfully: {full_path}")
    except Exception as e:
        logger.error(f"Failed to write report to volume: {e}")
        raise OSError(f"Failed to write report to {volume_path}/{filename}: {e}") from e

    return {
        "status": "success",
        "path": full_path,
        "filename": filename,
    }
