"""
HTML to DOCX Converter Tool

Converts HTML report content (including Chart.js configurations) to a Word
document (.docx) and saves it to a Unity Catalog Volume.

Strategy:
- Load corporate DOCX template (with styles, header/footer, page setup)
- Extract Chart.js configs via regex (supports both direct and variable patterns)
- Render charts with matplotlib using corporate color palette
- Convert HTML text/tables with htmldocx
- Insert chart images with captions and source citations
- Replace header placeholders with actual report title/date
- Save to UC Volume via Databricks SDK
"""

import os
import io
import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from htmldocx import HtmlToDocx
from databricks.sdk import WorkspaceClient
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_VOLUME_PATH = "/Volumes/agentbricks/volumes/agent_reports"

CHART_PLACEHOLDER = "___CHART_PLACEHOLDER_{}___ "

# Corporate color palette (from reference document)
CORPORATE_COLORS = [
    '#4E5B6F',  # Dark blue-gray (primary)
    '#007EEA',  # Bright blue
    '#898989',  # Medium gray
    '#D6ECFF',  # Light blue
    '#A7D6FF',  # Sky blue
    '#FFDF43',  # Yellow accent
    '#8E9BB0',  # Steel blue
    '#245375',  # Dark teal (heading color)
    '#4CAF50',  # Green
    '#FF6B6B',  # Red accent
]

# Template path (relative to the app directory)
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "template.docx")


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

    # Build a map of variable names to canvas IDs
    var_pattern = r"""(?:const|let|var)\s+(\w+)\s*=\s*document\.getElementById\s*\(\s*['"]([^'"]+)['"]\s*\)"""
    var_to_canvas = {}
    for var_match in re.finditer(var_pattern, html_content):
        var_to_canvas[var_match.group(1)] = var_match.group(2)

    # Pattern 1: direct
    pattern1 = r'new\s+Chart\s*\(\s*document\.getElementById\s*\(\s*[\x27"]([^\x27"]+)[\x27"]\s*\)'
    # Pattern 2: variable
    pattern2 = r'new\s+Chart\s*\(\s*(\w+)\s*,'

    found_charts = []

    for match in re.finditer(pattern1, html_content):
        canvas_id = match.group(1)
        rest = html_content[match.end():]
        found_charts.append((canvas_id, rest))

    for match in re.finditer(pattern2, html_content):
        var_name = match.group(1)
        if var_name == 'document':
            continue
        if var_name in var_to_canvas:
            canvas_id = var_to_canvas[var_name]
            if not any(c[0] == canvas_id for c in found_charts):
                rest = html_content[match.end():]
                found_charts.append((canvas_id, rest))

    for canvas_id, rest in found_charts:
        # Scope rest to only this chart's config
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
        data_arrays = re.findall(r'data\s*:\s*\[([\d.,\s\-]+)\]', rest[:10000])
        ds_labels = re.findall(r'label\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:10000])
        bg_colors = re.findall(r'backgroundColor\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:10000])
        border_colors = re.findall(r'borderColor\s*:\s*[\x27"]([^\x27"]+)[\x27"]', rest[:10000])

        datasets = []
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
        return CORPORATE_COLORS[0]
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
    return CORPORATE_COLORS[0]


def _render_chart_to_png_bytes(config: dict) -> bytes:
    """Render a chart config to PNG bytes using matplotlib with corporate styling."""
    chart_type = config.get("type", "bar")
    labels = config.get("labels", [])
    datasets = config.get("datasets", [])
    title = config.get("title")

    # Use corporate style
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Franklin Gothic Book', 'Arial', 'DejaVu Sans'],
        'font.size': 10,
        'axes.titlesize': 12,
        'axes.labelsize': 10,
    })

    fig, ax = plt.subplots(figsize=(10, 4.5))

    if chart_type == "bar":
        x = np.arange(len(labels))
        n_datasets = max(len(datasets), 1)
        width = 0.8 / n_datasets
        for i, ds in enumerate(datasets):
            offset = (i - n_datasets / 2 + 0.5) * width
            color = _parse_color(ds.get("backgroundColor", CORPORATE_COLORS[i % len(CORPORATE_COLORS)]))
            ax.bar(x + offset, ds.get("data", []), width,
                   label=ds.get("label", ""), color=color)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=9)

    elif chart_type == "line":
        for i, ds in enumerate(datasets):
            color = _parse_color(ds.get("backgroundColor", CORPORATE_COLORS[i % len(CORPORATE_COLORS)]))
            ax.plot(labels, ds.get("data", []), marker='o', linewidth=2.5,
                    label=ds.get("label", ""), color=color, markersize=5)

    elif chart_type in ("pie", "doughnut"):
        if datasets:
            ds = datasets[0]
            colors = [_parse_color(CORPORATE_COLORS[i % len(CORPORATE_COLORS)]) for i in range(len(labels))]
            wedgeprops = {"width": 0.4} if chart_type == "doughnut" else {}
            ax.pie(ds.get("data", []), labels=labels, colors=colors,
                   autopct='%1.1f%%', wedgeprops=wedgeprops,
                   textprops={'fontsize': 9})
            ax.set_aspect('equal')
    else:
        # Fallback to bar
        x = np.arange(len(labels))
        if datasets:
            color = _parse_color(datasets[0].get("backgroundColor", CORPORATE_COLORS[0]))
            ax.bar(x, datasets[0].get("data", []), color=color,
                   label=datasets[0].get("label", ""))
            ax.set_xticks(x)
            ax.set_xticklabels(labels, fontsize=9)

    if title:
        ax.set_title(title, fontsize=12, fontweight='bold', pad=12, color='#245375')

    if chart_type not in ("pie", "doughnut"):
        if any(ds.get("label") for ds in datasets):
            ax.legend(loc='upper left', fontsize=9, framealpha=0.9)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
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

    Returns: (clean_html_str, dict_of_chart_id_to_png_bytes_and_title)
    """
    charts = _extract_chart_configs(html_content)
    chart_data = {}

    # Render each chart
    for chart_info in charts:
        canvas_id = chart_info["canvas_id"]
        config = chart_info["config"]
        try:
            png_bytes = _render_chart_to_png_bytes(config)
            chart_data[canvas_id] = {
                "png_bytes": png_bytes,
                "title": config.get("title"),
            }
            logger.info(f"Rendered chart: {canvas_id}")
        except Exception as e:
            logger.warning(f"Failed to render chart {canvas_id}: {e}")

    # Process the HTML - replace canvas elements with text placeholders
    soup = BeautifulSoup(html_content, "html.parser")

    for canvas_id in chart_data:
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

    return clean_html, chart_data


def _load_template() -> Document:
    """Load the corporate DOCX template."""
    if os.path.exists(TEMPLATE_PATH):
        logger.info(f"Loading template from: {TEMPLATE_PATH}")
        return Document(TEMPLATE_PATH)
    else:
        logger.warning(f"Template not found at {TEMPLATE_PATH}, using blank document")
        return Document()


def _replace_header_placeholders(doc: Document, title: str, date_str: str):
    """Replace {{REPORT_TITLE}} and {{REPORT_DATE}} in the header."""
    for section in doc.sections:
        header = section.header
        for paragraph in header.paragraphs:
            for run in paragraph.runs:
                if "{{REPORT_TITLE}}" in run.text:
                    run.text = run.text.replace("{{REPORT_TITLE}}", title)
                if "{{REPORT_DATE}}" in run.text:
                    run.text = run.text.replace("{{REPORT_DATE}}", date_str)
        footer = section.footer
        for paragraph in footer.paragraphs:
            for run in paragraph.runs:
                if "{{COMPANY_NAME}}" in run.text:
                    run.text = run.text.replace("{{COMPANY_NAME}}", "")


def _extract_report_title(html_content: str) -> str:
    """Extract the report title from the HTML (first h1 tag)."""
    soup = BeautifulSoup(html_content, "html.parser")
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Sector Report"




def _insert_table_of_contents(doc: Document):
    """
    Insert a Table of Contents page after the first heading (title).
    Adds 'Obsah' heading, a TOC field code, and a page break.
    Word will auto-populate the TOC entries when the document is opened/updated.
    """
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn as _qn
    
    # Find the first Heading 1 paragraph (the title)
    insert_after_idx = None
    for i, para in enumerate(doc.paragraphs):
        if para.style and 'Heading 1' in para.style.name:
            insert_after_idx = i
            break
    
    if insert_after_idx is None:
        insert_after_idx = 0
    
    # We'll insert after the title paragraph
    # Get the element to insert after
    title_element = doc.paragraphs[insert_after_idx]._element
    
    # Create "Obsah" heading paragraph
    obsah_p = OxmlElement('w:p')
    obsah_pPr = OxmlElement('w:pPr')
    obsah_pStyle = OxmlElement('w:pStyle')
    obsah_pStyle.set(_qn('w:val'), 'Heading1')
    obsah_pPr.append(obsah_pStyle)
    obsah_p.append(obsah_pPr)
    obsah_r = OxmlElement('w:r')
    obsah_t = OxmlElement('w:t')
    obsah_t.text = 'Obsah'
    obsah_r.append(obsah_t)
    obsah_p.append(obsah_r)
    
    # Create TOC field paragraph
    toc_p = OxmlElement('w:p')
    
    # Field begin
    r_begin = OxmlElement('w:r')
    fldChar_begin = OxmlElement('w:fldChar')
    fldChar_begin.set(_qn('w:fldCharType'), 'begin')
    r_begin.append(fldChar_begin)
    toc_p.append(r_begin)
    
    # Field instruction
    r_instr = OxmlElement('w:r')
    instrText = OxmlElement('w:instrText')
    instrText.set(_qn('xml:space'), 'preserve')
    instrText.text = ' TOC \\o "2-3" \\h \\z \\u '
    r_instr.append(instrText)
    toc_p.append(r_instr)
    
    # Field separate
    r_sep = OxmlElement('w:r')
    fldChar_sep = OxmlElement('w:fldChar')
    fldChar_sep.set(_qn('w:fldCharType'), 'separate')
    r_sep.append(fldChar_sep)
    toc_p.append(r_sep)
    
    # Placeholder text (shown before Word updates the field)
    r_placeholder = OxmlElement('w:r')
    rPr_placeholder = OxmlElement('w:rPr')
    rFonts_ph = OxmlElement('w:rFonts')
    rFonts_ph.set(_qn('w:ascii'), 'Franklin Gothic Book')
    rFonts_ph.set(_qn('w:hAnsi'), 'Franklin Gothic Book')
    rPr_placeholder.append(rFonts_ph)
    r_placeholder.append(rPr_placeholder)
    t_placeholder = OxmlElement('w:t')
    t_placeholder.text = 'Aktualizujte obsah kliknutím pravým tlačítkem a výběrem "Aktualizovat pole"'
    r_placeholder.append(t_placeholder)
    toc_p.append(r_placeholder)
    
    # Field end
    r_end = OxmlElement('w:r')
    fldChar_end = OxmlElement('w:fldChar')
    fldChar_end.set(_qn('w:fldCharType'), 'end')
    r_end.append(fldChar_end)
    toc_p.append(r_end)
    
    # Page break paragraph
    pagebreak_p = OxmlElement('w:p')
    pb_r = OxmlElement('w:r')
    pb_br = OxmlElement('w:br')
    pb_br.set(_qn('w:type'), 'page')
    pb_r.append(pb_br)
    pagebreak_p.append(pb_r)
    
    # Insert in reverse order (after title): page break, TOC field, Obsah heading
    title_element.addnext(pagebreak_p)
    title_element.addnext(toc_p)
    title_element.addnext(obsah_p)
    
    logger.info("Inserted Table of Contents (Obsah) after title")

def _apply_corporate_styling(doc: Document):
    """
    Post-process the document to apply corporate fonts and styling.
    htmldocx creates paragraphs with inline formatting that overrides template styles,
    so we need to explicitly set the font on all runs.
    """
    for paragraph in doc.paragraphs:
        style_name = paragraph.style.name if paragraph.style else "Normal"

        # Determine font based on style
        if 'Heading' in style_name:
            target_font = 'Franklin Gothic Book'
            target_color = RGBColor(0x24, 0x53, 0x75)
        elif 'Chart Title' in style_name:
            target_font = 'Times New Roman'
            target_color = None
        elif 'Chart Source' in style_name:
            target_font = 'Times New Roman'
            target_color = RGBColor(0x20, 0x20, 0x20)
        else:
            target_font = 'Franklin Gothic Book'
            target_color = None

        for run in paragraph.runs:
            # Only set font if not already explicitly set
            if not run.font.name:
                run.font.name = target_font
            # Apply heading color
            if target_color and 'Heading' in style_name:
                if not run.font.color.rgb:
                    run.font.color.rgb = target_color

    # Also style table cells
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        if not run.font.name:
                            run.font.name = 'Franklin Gothic Book'
                        if not run.font.size:
                            run.font.size = Pt(9)



def _build_docx_with_charts(html_content: str, chart_data: dict, report_title: str) -> Document:
    """
    Build DOCX using the corporate template: convert HTML with htmldocx,
    then find placeholder paragraphs and replace them with chart images
    including title and source caption.
    """
    doc = _load_template()

    # Replace header placeholders
    date_str = datetime.now().strftime("%B %Y")
    _replace_header_placeholders(doc, report_title, date_str)

    # Convert HTML to DOCX content
    parser = HtmlToDocx()
    parser.add_html_to_document(html_content, doc)

    # Insert Table of Contents after the title
    _insert_table_of_contents(doc)

    # Find and replace placeholder paragraphs with charts
    for canvas_id, data in chart_data.items():
        placeholder_text = CHART_PLACEHOLDER.format(canvas_id).strip()
        png_bytes = data["png_bytes"]
        chart_title = data.get("title")

        for i, paragraph in enumerate(doc.paragraphs):
            if placeholder_text in paragraph.text:
                # Clear the placeholder text
                paragraph.clear()

                # Add chart title above (using Chart Title style if available)
                if chart_title:
                    # Insert title paragraph before the current one
                    title_para = paragraph.insert_paragraph_before(chart_title)
                    try:
                        title_para.style = doc.styles['Chart Title']
                    except KeyError:
                        # Fallback: manual formatting
                        for run in title_para.runs:
                            run.font.name = 'Times New Roman'
                            run.font.size = Pt(10)
                            run.font.bold = True

                # Add the chart image
                run = paragraph.add_run()
                image_stream = io.BytesIO(png_bytes)
                run.add_picture(image_stream, width=Cm(16.0))

                # Add source citation after the chart using OxmlElement
                from docx.oxml import OxmlElement
                from docx.oxml.ns import qn as _qn
                # Create a new paragraph element after current one
                new_p_elem = OxmlElement('w:p')
                # Add run with source text
                new_r_elem = OxmlElement('w:r')
                # Run properties (italic, font, size, color)
                rPr = OxmlElement('w:rPr')
                rFonts = OxmlElement('w:rFonts')
                rFonts.set(_qn('w:ascii'), 'Times New Roman')
                rFonts.set(_qn('w:hAnsi'), 'Times New Roman')
                rPr.append(rFonts)
                sz = OxmlElement('w:sz')
                sz.set(_qn('w:val'), '18')  # 9pt = 18 half-points
                rPr.append(sz)
                italic = OxmlElement('w:i')
                rPr.append(italic)
                color_elem = OxmlElement('w:color')
                color_elem.set(_qn('w:val'), '202020')
                rPr.append(color_elem)
                new_r_elem.append(rPr)
                # Text
                t_elem = OxmlElement('w:t')
                t_elem.text = "Zdroj: Vlastní zpracování"
                new_r_elem.append(t_elem)
                new_p_elem.append(new_r_elem)
                # Insert after current paragraph
                paragraph._element.addnext(new_p_elem)

                logger.info(f"Inserted chart with caption: {canvas_id}")
                break

    _apply_corporate_styling(doc)
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
    Convert HTML content (including Chart.js) to a styled Word document
    using the corporate template, and save to the configured UC Volume.
    """
    volume_path = get_volume_path()
    logger.info(f"Target volume path: {volume_path}")

    try:
        # Extract report title for header
        report_title = _extract_report_title(html_content)

        soup = BeautifulSoup(html_content, "html.parser")
        has_scripts = bool(soup.find_all("script"))

        if has_scripts:
            logger.info("HTML contains scripts - rendering charts with matplotlib")
            clean_html, chart_data = _prepare_html_and_charts(html_content)
            doc = _build_docx_with_charts(clean_html, chart_data, report_title)
        else:
            logger.info("HTML is static - converting directly with template")
            body = soup.find("body")
            clean_html = str(body) if body else html_content
            doc = _load_template()
            # Replace header
            date_str = datetime.now().strftime("%B %Y")
            _replace_header_placeholders(doc, report_title, date_str)
            parser = HtmlToDocx()
            parser.add_html_to_document(clean_html, doc)
            _insert_table_of_contents(doc)
            _apply_corporate_styling(doc)

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
