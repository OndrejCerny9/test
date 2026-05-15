"""
HTML Report Saver Tool

Saves generated HTML report content to a Unity Catalog Volume.
The target volume path is configurable via the REPORT_VOLUME_PATH environment variable.
"""

import os
import logging

logger = logging.getLogger(__name__)

DEFAULT_VOLUME_PATH = "/Volumes/agentbricks/test/agent_reports"


def get_volume_path() -> str:
    """Get the configured volume path from environment or use default."""
    return os.environ.get("REPORT_VOLUME_PATH", DEFAULT_VOLUME_PATH)


def save_html_report(filename: str, html_content: str) -> dict:
    """
    Save HTML content to the configured Unity Catalog Volume.

    Args:
        filename: Name of the HTML file (must end with .html, already sanitized).
        html_content: The HTML string to write.

    Returns:
        dict with keys: status, path, filename.

    Raises:
        OSError: If writing to the volume fails.
    """
    volume_path = get_volume_path()

    # Ensure the output directory exists
    os.makedirs(volume_path, exist_ok=True)
    logger.info(f"Volume path verified: {volume_path}")

    # Build full file path
    full_path = os.path.join(volume_path, filename)

    # Write HTML content with UTF-8 encoding
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info(f"Report saved successfully: {full_path}")
    except OSError as e:
        logger.error(f"Failed to write report to {full_path}: {e}")
        raise OSError(f"Failed to write report to {full_path}: {e}") from e

    return {
        "status": "success",
        "path": full_path,
        "filename": filename,
    }
