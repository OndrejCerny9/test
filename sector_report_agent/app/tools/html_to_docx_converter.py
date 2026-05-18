"""
HTML to DOCX Converter Tool

Converts HTML report content (including Chart.js configurations) to a Word
document (.docx) and saves it to a Unity Catalog Volume.

Strategy:
- Split HTML at chart positions into text segments and chart segments
- Convert text segments with htmldocx
- Render chart segments with matplotlib and insert as images via python-docx
- Save to UC Volume via Databricks SDK
"""

import os
import io
import re
import base64
import logging
from bs4 import BeautifulSoup, NavigableString
from docx import Document
from docx.shared import Inches
from htmldocx import HtmlToDocx
from databricks.sdk import WorkspaceClient
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_VOLUME_PATH = "/Volumes/agentbricks/volumes/agent_reports"

CHART_PLACEHOLDER = "___CHART_PLACEHOLDER_{}___ "


def get_volume_path() -> str:
    """Get the configured volume path from environment or use default."""
    return os.environ.get("REPORT_VOLUME_PATH", DEFAULT_VOLUME_PATH)



def _find_chart_config_end(text: str) -> int:
    """Find the end of a Chart config object by matching braces."""
    brace_count = 0
    started = False
    for i, ch in enumerate(text):
        if ch == '{':
            brace_count += 1
            started = True
        elif ch == '}':
            brace_count -= 1
            if started and brace_count == 0:
                remaining = text[i:]
                end_match = re.search(r'\)\s*;', remaining)
                if end_match:
                    return i + end_match.end()
                return i + 1
    return len(text)


def _extract_chart_configs(html_content: str) -> list:
    """
    Extract Chart.js configurations from <script> blocks.
    Returns list of dicts with canvas_id and chart config data.

    Handles two patterns:
    1. new Chart(document.getElementById('id'), {...})
    2. const ctx = document.getElementById('id').getContext('2d'); new Chart(ctx, {...})
    """
    charts = []

    # First, build a map of variable names to canvas IDs
    # Matches: const/let/var name = document.getElementById('id') or .getContext('2d')
    var_pattern = r'''(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\s*\(\s*['"]([^'"]+)['"]\s*\)'''
    var_to_canvas = {}
    for var_match in re.finditer(var_pattern, html_content):
        var_name = var_match.group(1)
        canvas_id = var_match.group(2)
        var_to_canvas[var_name] = canvas_id

    # Pattern 1: new Chart(document.getElementById('id'), {...})
    pattern1 = r'new\s+Chart\s*\(\s*document\.getElementById\s*\(\s*[\x27"]([^\x27"]+)[\x27"]\s*\)'
    # Pattern 2: new Chart(variableName, {...})
    pattern2 = r'new\s+Chart\s*\(\s*(\w+)\s*,'

    found_charts = []  # list of (canvas_id, rest_of_content)

    for match in re.finditer(pattern1, html_content):
        canvas_id = match.group(1)
        rest = html_content[match.end():]
        found_charts.append((canvas_id, rest))

    for match in re.finditer(pattern2, html_content):
        var_name = match.group(1)
        # Skip if var_name is 'document' (would be caught by pattern1)
        if var_name == 'document':
            continue
        if var_name in var_to_canvas:
            canvas_id = var_to_canvas[var_name]
            # Check we haven't already found this canvas from pattern1
            if not any(c[0] == canvas_id for c in found_charts):
                rest = html_content[match.end():]
                found_charts.append((canvas_id, rest))

    for canvas_id, rest in found_charts:
        # Scope rest to only this chart's config (not subsequent charts)
        config_end = _find_chart_config_end(rest)
        rest = rest[:config_end]


        # Extract chart type
        type_match = re.search(r'type\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:1000])
        chart_type = type_match.group(1) if type_match else "bar"

        # Extract labels
        labels_match = re.search(r'labels\s*:\s*\[([^\]]+)\]', rest[:5000])
        labels = []
        if labels_match:
            labels = [l.strip().strip("\x27\"") for l in labels_match.group(1).split(",")]

        # Extract datasets
        datasets = []
        data_arrays = re.findall(r'data\s*:\s*\[([\d.,\s\-]+)\]', rest[:10000])
        ds_labels = re.findall(r'label\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:10000])
        bg_colors = re.findall(r'backgroundColor\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:10000])
        border_colors = re.findall(r'borderColor\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:10000])

        for i, data_str in enumerate(data_arrays):
            try:
                data_vals = [float(x.strip()) for x in data_str.split(",") if x.strip()]
                dataset = {"data": data_vals}
                if i < len(ds_labels):
                    dataset["label"] = ds_labels[i]
                if i < len(bg_colors):
                    dataset["backgroundColor"] = bg_colors[i]
                elif i < len(border_colors):
                    dataset["backgroundColor"] = border_colors[i]
                datasets.append(dataset)
            except ValueError:
                continue

        # Extract title
        title_text = None
        title_match = re.search(r'text\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:10000])
        if title_match:
            title_text = title_match.group(1)

        if labels and datasets:
            config = {
                "type": chart_type,
                "labels": labels,
                "datasets": datasets,
                "title": title_text,
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


def _render_chart_to_png_bytes(config: dict) -> bytes:
    """Render a chart config to PNG bytes using matplotlib."""
    chart_type = config.get("type", "bar")
    labels = config.get("labels", [])
    datasets = config.get("datasets", [])
    title = config.get("title")

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
        x = np.arange(len(labels))
        if datasets:
            color = _parse_color(datasets[0].get("backgroundColor", default_colors[0]))
            ax.bar(x, datasets[0].get("data", []), color=color,
                   label=datasets[0].get("label", ""))
            ax.set_xticks(x)
            ax.set_xticklabels(labels, fontsize=11)

    if title:
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)

    if chart_type not in ("pie", "doughnut"):
        if any(ds.get("label") for ds in datasets):
            ax.legend(loc='upper left', fontsize=10)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3)
    plt.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buffer.seek(0)
    return buffer.read()


def _prepare_html_and_charts(html_content: str) -> tuple:
    """
    Process HTML: extract charts, replace canvas elements with placeholders,
    remove scripts/styles, return clean HTML and chart image bytes.

    Returns: (clean_html_str, dict_of_chart_id_to_png_bytes)
    """
    charts = _extract_chart_configs(html_content)
    chart_images = {}

    # Render each chart
    for chart_info in charts:
        canvas_id = chart_info["canvas_id"]
        config = chart_info["config"]
        try:
            png_bytes = _render_chart_to_png_bytes(config)
            chart_images[canvas_id] = png_bytes
            logger.info(f"Rendered chart: {canvas_id}")
        except Exception as e:
            logger.warning(f"Failed to render chart {canvas_id}: {e}")

    # Now process the HTML - replace canvas elements with text placeholders
    soup = BeautifulSoup(html_content, "html.parser")

    for canvas_id in chart_images:
        canvas = soup.find("canvas", {"id": canvas_id})
        if canvas:
            placeholder = soup.new_tag("p")
            placeholder.string = CHART_PLACEHOLDER.format(canvas_id)
            parent = canvas.parent
            if parent and parent.name == "div":
                parent.replace_with(placeholder)
            else:
                canvas.replace_with(placeholder)

    # Remove scripts and styles
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()

    body = soup.find("body")
    clean_html = str(body) if body else str(soup)

    return clean_html, chart_images


def _build_docx_with_charts(html_content: str, chart_images: dict) -> Document:
    """
    Build DOCX: convert HTML with htmldocx, then find placeholder paragraphs
    and replace them with chart images.
    """
    doc = Document()
    parser = HtmlToDocx()
    parser.add_html_to_document(html_content, doc)

    # Now find and replace placeholder paragraphs with images
    for canvas_id, png_bytes in chart_images.items():
        placeholder_text = CHART_PLACEHOLDER.format(canvas_id).strip()

        for paragraph in doc.paragraphs:
            if placeholder_text in paragraph.text:
                # Clear the paragraph text
                paragraph.clear()
                # Add image to this paragraph
                run = paragraph.add_run()
                image_stream = io.BytesIO(png_bytes)
                run.add_picture(image_stream, width=Inches(6.0))
                logger.info(f"Inserted chart image for: {canvas_id}")
                break

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
    Convert HTML content (including Chart.js) to a Word document
    and save to the configured Unity Catalog Volume.
    """
    volume_path = get_volume_path()
    logger.info(f"Target volume path: {volume_path}")

    try:
        soup = BeautifulSoup(html_content, "html.parser")
        has_scripts = bool(soup.find_all("script"))

        if has_scripts:
            logger.info("HTML contains scripts - rendering charts with matplotlib")
            clean_html, chart_images = _prepare_html_and_charts(html_content)
            doc = _build_docx_with_charts(clean_html, chart_images)
        else:
            logger.info("HTML is static - converting directly")
            body = soup.find("body")
            clean_html = str(body) if body else html_content
            doc = Document()
            parser = HtmlToDocx()
            parser.add_html_to_document(clean_html, doc)

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
