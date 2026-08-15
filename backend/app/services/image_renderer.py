"""Playwright-based HTML-to-PNG renderer."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class RenderingError(Exception):
    """Raised when Playwright fails to render an HTML document to PNG."""


async def render_html_to_png(
    html: str,
    output_path: Path,
    width: int,
    height: int,
) -> Path:
    """
    Render an HTML document to a PNG file using headless Chromium.

    Args:
        html: Complete HTML document string.
        output_path: Destination file path for the PNG.
        width: Viewport width in pixels.
        height: Viewport height in pixels.

    Returns:
        The output_path after the file has been written.

    Raises:
        RenderingError: If Playwright raises any exception.
    """
    try:
        from playwright.async_api import async_playwright  # lazy import

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": width, "height": height})
            await page.set_content(html, wait_until="networkidle")
            await page.screenshot(path=str(output_path), full_page=False)
            await browser.close()
        return output_path
    except ImportError as exc:
        raise RenderingError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc
    except Exception as exc:
        raise RenderingError(f"Playwright rendering failed: {exc}") from exc
