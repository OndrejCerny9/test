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
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_VOLUME_PATH = "/Volumes/agentbricks/volumes/agent_reports"


def get_volume_path() -> str:
    """Get the configured volume path from environment or use default."""
    return os.environ.get("REPORT_VOLUME_PATH", DEFAULT_VOLUME_PATH)


def _extract_chart_configs(html_content: str) -> list[dict]:
    """
    Extract Chart.js configurations from <script> blocks in the HTML.
    
    Looks for patterns like:
        new Chart(document.getElementById('chartId'), { ... });
    
    Returns a list of dicts with keys: canvas_id, config (parsed chart config).
    """
    charts = []
    
    # Match: new Chart(document.getElementById('id'), { config })
    # We need to handle nested braces, so we use a simple brace-counting approach
    pattern = r"new\s+Chart\s*\(\s*document\.getElementById\(['"]([^'"]+)['"]\)\s*,\s*"
    
    for match in re.finditer(pattern, html_content):
        canvas_id = match.group(1)
        start_pos = match.end()
        
        # Find the matching closing brace for the config object
        brace_count = 0
        config_start = None
        config_end = None
        
        for i in range(start_pos, len(html_content)):
            if html_content[i] == '{':
                if brace_count == 0:
                    config_start = i
                brace_count += 1
            elif html_content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    config_end = i + 1
                    break
        
        if config_start is not None and config_end is not None:
            config_str = html_content[config_start:config_end]
            
            # Clean up JS-specific syntax for JSON parsing
            # Remove trailing commas before } or ]
            config_str = re.sub(r',\s*([}\]])', r'\1', config_str)
            # Quote unquoted keys
            config_str = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', config_str)
            # Replace single quotes with double quotes
            config_str = config_str.replace("'", '"')
            # Remove JS function calls (e.g., callbacks) - replace with null
            config_str = re.sub(r'"[a-zA-Z]+":[ \t]*function\s*\([^)]*\)\s*\{[^}]*\}', '"_removed": null', config_str)
            
            try:
                config = json.loads(config_str)
                charts.append({"canvas_id": canvas_id, "config": config})
                logger.info(f"Extracted chart config for canvas: {canvas_id}")
            except json.JSONDecodeError as e:
                logger.warning(f"Could not parse chart config for {canvas_id}: {e}")
                # Try a simpler extraction - just get type, labels, and data
                simple_config = _extract_simple_config(html_content[config_start:config_end], canvas_id)
                if simple_config:
                    charts.append(simple_config)
    
    return charts


def _extract_simple_config(config_str: str, canvas_id: str) -> dict | None:
    """
    Fallback: extract chart essentials using regex when JSON parsing fails.
    """
    try:
        # Extract type
        type_match = re.search(r"type\s*:\s*['"]([^'"]+)['"]", config_str)
        chart_type = type_match.group(1) if type_match else "bar"
        
        # Extract labels
        labels_match = re.search(r"labels\s*:\s*\[([^\]]+)\]", config_str)
        labels = []
        if labels_match:
            labels = [l.strip().strip("'"") for l in labels_match.group(1).split(",")]
        
        # Extract datasets
        datasets = []
        # Find data arrays
        data_matches = re.findall(r"data\s*:\s*\[([\d.,\s]+)\]", config_str)
        label_matches = re.findall(r"label\s*:\s*['"]([^'"]+)['"]", config_str)
        bg_color_matches = re.findall(r"backgroundColor\s*:\s*['"]([^'"]+)['"]", config_str)
        
        for i, data_str in enumerate(data_matches):
            dataset = {
                "data": [float(x.strip()) for x in data_str.split(",") if x.strip()],
                "label": label_matches[i] if i < len(label_matches) else f"Series {i+1}",
            }
            if i < len(bg_color_matches):
                dataset["backgroundColor"] = bg_color_matches[i]
            datasets.append(dataset)
        
        if labels and datasets:
            config = {
                "type": chart_type,
                "data": {"labels": labels, "datasets": datasets}
            }
            return {"canvas_id": canvas_id, "config": config}
    except Exception as e:
        logger.warning(f"Simple config extraction failed for {canvas_id}: {e}")
    
    return None


def _render_chart_to_base64(config: dict) -> str:
    """
    Render a Chart.js-like configuration to a PNG image using matplotlib.
    Returns a base64-encoded PNG string.
    """
    chart_type = config.get("type", "bar")
    data = config.get("data", {})
    labels = data.get("labels", [])
    datasets = data.get("datasets", [])
    options = config.get("options", {})
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    # Color palette
    default_colors = [
        '#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe',
        '#00f2fe', '#43e97b', '#fa709a', '#fee140', '#a18cd1'
    ]
    
    if chart_type == "bar":
        x = np.arange(len(labels))
        width = 0.8 / max(len(datasets), 1)
        
        for i, ds in enumerate(datasets):
            offset = (i - len(datasets) / 2 + 0.5) * width
            color = _parse_color(ds.get("backgroundColor", default_colors[i % len(default_colors)]))
            border_color = _parse_color(ds.get("borderColor", color))
            ax.bar(x + offset, ds.get("data", []), width, 
                   label=ds.get("label", ""), color=color, edgecolor=border_color, linewidth=1.5)
        
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=11, fontweight='bold')
        
    elif chart_type == "line":
        for i, ds in enumerate(datasets):
            color = _parse_color(ds.get("borderColor", default_colors[i % len(default_colors)]))
            ax.plot(labels, ds.get("data", []), marker='o', linewidth=2.5,
                    label=ds.get("label", ""), color=color, markersize=6)
        
    elif chart_type in ("pie", "doughnut"):
        if datasets:
            ds = datasets[0]
            colors_raw = ds.get("backgroundColor", default_colors[:len(labels)])
            if isinstance(colors_raw, list):
                colors = [_parse_color(c) for c in colors_raw]
            else:
                colors = [_parse_color(colors_raw)] * len(labels)
            
            wedgeprops = {"width": 0.4} if chart_type == "doughnut" else {}
            ax.pie(ds.get("data", []), labels=labels, colors=colors, 
                   autopct='%1.1f%%', wedgeprops=wedgeprops, textprops={'fontsize': 10})
            ax.set_aspect('equal')
    
    elif chart_type == "scatter":
        for i, ds in enumerate(datasets):
            color = _parse_color(ds.get("backgroundColor", default_colors[i % len(default_colors)]))
            point_data = ds.get("data", [])
            if point_data and isinstance(point_data[0], dict):
                xs = [p.get("x", 0) for p in point_data]
                ys = [p.get("y", 0) for p in point_data]
            else:
                xs = list(range(len(point_data)))
                ys = point_data
            ax.scatter(xs, ys, label=ds.get("label", ""), color=color, s=60)
    
    else:
        # Fallback to bar chart
        x = np.arange(len(labels))
        if datasets:
            color = _parse_color(datasets[0].get("backgroundColor", default_colors[0]))
            ax.bar(x, datasets[0].get("data", []), color=color, 
                   label=datasets[0].get("label", ""))
            ax.set_xticks(x)
            ax.set_xticklabels(labels, fontsize=11)
    
    # Apply title from options
    plugins = options.get("plugins", {})
    title_cfg = plugins.get("title", {})
    if title_cfg.get("display") and title_cfg.get("text"):
        ax.set_title(title_cfg["text"], fontsize=14, fontweight='bold', pad=15)
    
    # Legend
    legend_cfg = plugins.get("legend", {})
    if legend_cfg.get("position") != "hidden" and chart_type not in ("pie", "doughnut"):
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


def _parse_color(color_str) -> str:
    """Parse rgba/rgb/hex color string to matplotlib-compatible format."""
    if not isinstance(color_str, str):
        return '#667eea'
    
    color_str = color_str.strip()
    
    # Handle rgba(r, g, b, a)
    rgba_match = re.match(r'rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)', color_str)
    if rgba_match:
        r, g, b = int(rgba_match.group(1)), int(rgba_match.group(2)), int(rgba_match.group(3))
        a = float(rgba_match.group(4)) if rgba_match.group(4) else 1.0
        return (r/255, g/255, b/255, a)
    
    # Hex color
    if color_str.startswith('#'):
        return color_str
    
    return color_str


def _html_has_scripts(html_content: str) -> bool:
    """Check if HTML contains script tags (indicating JS-rendered content)."""
    soup = BeautifulSoup(html_content, "html.parser")
    return bool(soup.find_all("script"))


def _render_charts_into_html(html_content: str) -> str:
    """
    Extract Chart.js configs, render with matplotlib, and replace canvas
    elements with base64 images in the HTML.
    """
    charts = _extract_chart_configs(html_content)
    soup = BeautifulSoup(html_content, "html.parser")
    
    for chart_info in charts:
        canvas_id = chart_info["canvas_id"]
        config = chart_info["config"]
        
        # Render chart to base64
        try:
            img_base64 = _render_chart_to_base64(config)
            
            # Find and replace the canvas element
            canvas = soup.find("canvas", {"id": canvas_id})
            if canvas:
                img_tag = soup.new_tag("img")
                img_tag["src"] = f"data:image/png;base64,{img_base64}"
                img_tag["style"] = "max-width: 100%; display: block; margin: 10px auto;"
                
                # Replace the canvas (or its parent container)
                parent = canvas.parent
                if parent and parent.name == "div":
                    parent.replace_with(img_tag)
                else:
                    canvas.replace_with(img_tag)
                    
                logger.info(f"Rendered chart for canvas: {canvas_id}")
        except Exception as e:
            logger.warning(f"Failed to render chart {canvas_id}: {e}")
    
    # Remove all script tags
    for script in soup.find_all("script"):
        script.decompose()
    
    # Remove style tags
    for style in soup.find_all("style"):
        style.decompose()
    
    # Return body content
    body = soup.find("body")
    return str(body) if body else str(soup)


def _build_docx_from_html(rendered_html: str) -> Document:
    """
    Build a DOCX document from rendered HTML.
    Handles base64 images and converts text/tables via htmldocx.
    """
    doc = Document()
    parser = HtmlToDocx()
    parser.add_html_to_document(rendered_html, doc)
    return doc


def _save_to_volume(doc: Document, volume_path: str, filename: str) -> str:
    """
    Save a DOCX document to a Unity Catalog Volume using the Databricks SDK.
    """
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

    Args:
        filename: Name of the output file (must end with .docx, already sanitized).
        html_content: The HTML string to convert (may include Chart.js scripts).

    Returns:
        dict with keys: status, path, filename.

    Raises:
        OSError: If writing to the volume fails.
        ValueError: If HTML conversion fails.
    """
    volume_path = get_volume_path()
    logger.info(f"Target volume path: {volume_path}")

    try:
        if _html_has_scripts(html_content):
            logger.info("HTML contains scripts - extracting and rendering charts with matplotlib")
            rendered_html = _render_charts_into_html(html_content)
        else:
            logger.info("HTML is static - converting directly")
            soup = BeautifulSoup(html_content, "html.parser")
            body = soup.find("body")
            rendered_html = str(body) if body else html_content

        # Build the DOCX from the rendered HTML
        doc = _build_docx_from_html(rendered_html)

    except Exception as e:
        logger.error(f"HTML to DOCX conversion failed: {e}")
        raise ValueError(f"HTML to DOCX conversion failed: {e}") from e

    # Save the DOCX to the UC Volume via SDK
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
