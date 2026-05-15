"""
HTML to DOCX Converter Tool

Converts HTML report content (including JavaScript-rendered charts) to a Word
document (.docx) and saves it to a Unity Catalog Volume.

Flow:
1. Render HTML in headless Chromium via Playwright (executes Chart.js, etc.)
2. Convert <canvas> elements to inline <img> base64 PNGs
3. Strip scripts and extract the rendered body content
4. Convert the cleaned HTML to DOCX using htmldocx
5. Save the .docx file to the configured UC Volume via Databricks SDK
"""

import os
import io
import logging
from bs4 import BeautifulSoup
from docx import Document
from htmldocx import HtmlToDocx
from playwright.async_api import async_playwright
from databricks.sdk import WorkspaceClient
import asyncio

logger = logging.getLogger(__name__)

DEFAULT_VOLUME_PATH = "/Volumes/agentbricks/volumes/agent_reports"


def get_volume_path() -> str:
    """Get the configured volume path from environment or use default."""
    return os.environ.get("REPORT_VOLUME_PATH", DEFAULT_VOLUME_PATH)


async def _render_html_with_playwright(html_content: str) -> str:
    """
    Render HTML in headless Chromium, convert canvas elements to base64 images,
    and return the modified HTML with charts as inline images.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
        )
        page = await browser.new_page(viewport={"width": 1200, "height": 800})

        # Load the HTML content
        await page.set_content(html_content, wait_until="networkidle")

        # Wait for Chart.js or other JS charts to render
        await page.wait_for_timeout(2000)

        # Convert all canvas elements to img elements with base64 PNGs
        rendered_html = await page.evaluate("""
            () => {
                const canvases = document.querySelectorAll('canvas');
                canvases.forEach(canvas => {
                    try {
                        const dataUrl = canvas.toDataURL('image/png');
                        const img = document.createElement('img');
                        img.src = dataUrl;
                        img.style.width = canvas.style.width || canvas.getAttribute('width') + 'px' || '100%';
                        img.style.maxWidth = '100%';
                        img.style.display = 'block';
                        img.style.margin = '10px auto';
                        if (canvas.parentElement && canvas.parentElement.classList.contains('chart-container')) {
                            canvas.parentElement.replaceChild(img, canvas);
                        } else {
                            canvas.parentNode.replaceChild(img, canvas);
                        }
                    } catch (e) {
                        console.error('Failed to convert canvas:', e);
                    }
                });

                // Remove all script tags
                document.querySelectorAll('script').forEach(s => s.remove());

                return document.body.innerHTML;
            }
        """)

        await browser.close()

    return rendered_html


def _html_has_scripts(html_content: str) -> bool:
    """Check if HTML contains script tags (indicating JS-rendered content)."""
    soup = BeautifulSoup(html_content, "html.parser")
    return bool(soup.find_all("script"))


def _build_docx_from_html(rendered_html: str) -> Document:
    """
    Build a DOCX document from rendered HTML.
    Handles base64 images from chart rendering and converts text/tables via htmldocx.
    """
    soup = BeautifulSoup(rendered_html, "html.parser")
    doc = Document()

    # Remove style tags (styling is handled by docx formatting)
    for style_tag in soup.find_all("style"):
        style_tag.decompose()

    # Clean up the HTML for htmldocx
    clean_html = str(soup)

    # Use htmldocx to convert - it handles inline base64 images
    parser = HtmlToDocx()
    parser.add_html_to_document(clean_html, doc)

    return doc


def _save_to_volume(doc: Document, volume_path: str, filename: str) -> str:
    """
    Save a DOCX document to a Unity Catalog Volume using the Databricks SDK.

    Args:
        doc: The python-docx Document object.
        volume_path: The UC Volume path (e.g., /Volumes/catalog/schema/volume).
        filename: The filename to save as.

    Returns:
        The full path where the file was saved.
    """
    # Serialize DOCX to bytes in memory
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    # Build the full path
    full_path = f"{volume_path}/{filename}"

    # Upload via Databricks SDK Files API
    w = WorkspaceClient()
    w.files.upload(full_path, buffer, overwrite=True)

    return full_path


def convert_html_to_docx(filename: str, html_content: str) -> dict:
    """
    Convert HTML content (including JS-rendered charts) to a Word document
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
        # If HTML has scripts (Chart.js, etc.), render with Playwright first
        if _html_has_scripts(html_content):
            logger.info("HTML contains scripts - rendering with Playwright")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                rendered_html = loop.run_until_complete(
                    _render_html_with_playwright(html_content)
                )
            finally:
                loop.close()
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
