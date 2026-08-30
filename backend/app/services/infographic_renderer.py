"""
Pillow-based text renderer for infographic composition.

Implements:
- Automatic word wrapping
- Font-size reduction
- Text layout and positioning
- High-contrast text colors
- Safe margins and padding
- Font fallback system
"""
import logging
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class FontHelper:
    """Font fallback system for cross-platform compatibility."""

    def __init__(self):
        """Initialize font helper with fallback candidates."""
        # List of fonts to try in order of preference
        self.font_candidates = [
            "DejaVuSans.ttf",
            "DejaVuSansBold.ttf",
            "LiberationSans-Regular.ttf",
            "LiberationSans-Bold.ttf",
            "NotoSans-Regular.ttf",
            "NotoSans-Bold.ttf",
        ]

        # Common font paths across platforms
        self.font_search_paths = [
            Path("/usr/share/fonts"),  # Linux
            Path("C:\\Windows\\Fonts"),  # Windows
            Path("/Library/Fonts"),  # macOS
            Path("/System/Library/Fonts"),  # macOS system fonts
        ]

        self._font_cache = {}

    def _find_font_file(self, font_name: str) -> Optional[Path]:
        """Find a font file on the system."""
        for search_path in self.font_search_paths:
            if not search_path.exists():
                continue

            # Direct match
            font_path = search_path / font_name
            if font_path.exists():
                return font_path

            # Recursive search
            try:
                for path in search_path.rglob(font_name):
                    return path
            except PermissionError:
                continue

        return None

    def get_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """
        Get a TrueType font of the given size with fallback.

        Args:
            size: Font size in pixels
            bold: Use bold variant if available

        Returns:
            PIL ImageFont object
        """
        cache_key = (size, bold)
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        candidates = [
            "DejaVuSansBold.ttf" if bold else "DejaVuSans.ttf",
            "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf",
            "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf",
        ]

        for font_name in candidates:
            font_path = self._find_font_file(font_name)
            if font_path:
                try:
                    font = ImageFont.truetype(str(font_path), size)
                    self._font_cache[cache_key] = font
                    logger.debug("Loaded font: %s (size=%d, bold=%s)", font_path, size, bold)
                    return font
                except Exception as exc:
                    logger.warning("Failed to load font %s: %s", font_path, exc)
                    continue

        # Fallback: use default font
        logger.warning(
            "No TrueType fonts found. Using PIL default font. Text rendering may look poor."
        )
        return ImageFont.load_default()

    def close(self) -> None:
        """Clear font cache."""
        self._font_cache.clear()


class InfographicRenderer:
    """Compose infographic with text using Pillow."""

    def __init__(
        self,
        width: int = 1536,
        height: int = 864,
        title_text_color: tuple[int, int, int] = (255, 255, 255),
        panel_heading_color: tuple[int, int, int] = (255, 255, 255),
        panel_text_color: tuple[int, int, int] = (255, 255, 255),
        summary_text_color: tuple[int, int, int] = (255, 255, 255),
    ):
        """
        Initialize renderer.

        Args:
            width: Canvas width (default 1536)
            height: Canvas height (default 864)
            title_text_color: RGB tuple for title text
            panel_heading_color: RGB tuple for panel heading text
            panel_text_color: RGB tuple for panel description text
            summary_text_color: RGB tuple for summary text
        """
        self.width = width
        self.height = height
        self.title_text_color = title_text_color
        self.panel_heading_color = panel_heading_color
        self.panel_text_color = panel_text_color
        self.summary_text_color = summary_text_color

        self.font_helper = FontHelper()

        # Layout dimensions (in pixels)
        self.margin = 20
        self.padding = 15
        self.line_spacing = 1.3

        # Banner dimensions
        self.title_banner_height = 100
        self.summary_banner_height = 80

        # Panel layout
        self.content_height = (
            height - self.title_banner_height - self.summary_banner_height
        )

    def _wrap_text(self, text: str, max_width: int, font: ImageFont.FreeTypeFont) -> list[str]:
        """
        Wrap text to fit within max_width using the given font.

        Args:
            text: Text to wrap
            max_width: Maximum pixel width
            font: PIL ImageFont to use for measurement

        Returns:
            List of wrapped lines
        """
        lines = []
        for paragraph in text.split("\n"):
            current_line = ""
            for word in paragraph.split():
                test_line = f"{current_line} {word}".strip()
                bbox = font.getbbox(test_line)
                test_width = bbox[2] - bbox[0]

                if test_width <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word

            if current_line:
                lines.append(current_line)

        return lines

    def _draw_wrapped_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        position: tuple[int, int],
        max_width: int,
        max_height: int,
        font: ImageFont.FreeTypeFont,
        color: tuple[int, int, int],
        align: str = "left",
    ) -> tuple[bool, int]:
        """
        Draw wrapped text in a region, with automatic font reduction if needed.

        Args:
            draw: PIL ImageDraw object
            text: Text to draw
            position: (x, y) starting position
            max_width: Maximum width for text
            max_height: Maximum height for text
            font: Starting font
            color: RGB color tuple
            align: Text alignment: "left", "center", "right"

        Returns:
            (success, height_used) - success=True if text fits, height_used=pixels used
        """
        x, y = position
        current_font = font
        font_size = current_font.size if hasattr(current_font, "size") else 20

        # Try to fit text with current font size
        while font_size > 8:  # Minimum font size
            lines = self._wrap_text(text, max_width, current_font)

            # Calculate total height
            total_height = 0
            for line in lines:
                bbox = current_font.getbbox(line)
                line_height = bbox[3] - bbox[1]
                total_height += int(line_height * self.line_spacing)

            if total_height <= max_height:
                # Text fits! Draw it
                current_y = y
                for line in lines:
                    bbox = current_font.getbbox(line)
                    line_height = bbox[3] - bbox[1]

                    # Calculate x position based on alignment
                    if align == "center":
                        bbox_line = current_font.getbbox(line)
                        line_width = bbox_line[2] - bbox_line[0]
                        current_x = x + (max_width - line_width) // 2
                    elif align == "right":
                        bbox_line = current_font.getbbox(line)
                        line_width = bbox_line[2] - bbox_line[0]
                        current_x = x + max_width - line_width
                    else:
                        current_x = x

                    draw.text(
                        (current_x, current_y),
                        line,
                        font=current_font,
                        fill=color,
                    )
                    current_y += int(line_height * self.line_spacing)

                return True, current_y - y

            # Text doesn't fit, reduce font size
            font_size -= 2
            current_font = self.font_helper.get_font(font_size)

        # Text doesn't fit even at minimum size
        logger.warning("Text overflow: could not fit text at minimum size")
        return False, max_height

    def compose(
        self,
        background_image: Image.Image,
        title: str,
        panels: list[dict],
        summary: str,
        subtitle: Optional[str] = None,
    ) -> Image.Image:
        """
        Compose infographic with text overlays.

        Args:
            background_image: PIL Image with illustrated infographic background
            title: Main title text
            panels: List of dicts with keys: number, heading, description
            summary: Summary text
            subtitle: Optional subtitle text

        Returns:
            PIL Image with composed text
        """
        # Ensure image is correct size and mode
        if background_image.size != (self.width, self.height):
            logger.warning(
                "Background image size mismatch: expected (%d, %d), got %s",
                self.width,
                self.height,
                background_image.size,
            )
            background_image = background_image.resize((self.width, self.height))

        if background_image.mode != "RGB":
            background_image = background_image.convert("RGB")

        # Create a copy for composition
        image = background_image.copy()
        draw = ImageDraw.Draw(image)

        # Calculate regions
        title_box = (
            self.margin,
            self.margin,
            self.width - self.margin,
            self.title_banner_height,
        )

        panels_box = (
            self.margin,
            self.title_banner_height,
            self.width - self.margin,
            self.height - self.summary_banner_height,
        )

        summary_box = (
            self.margin,
            self.height - self.summary_banner_height,
            self.width - self.margin,
            self.height - self.margin,
        )

        # Draw title
        title_font = self.font_helper.get_font(48, bold=True)
        title_width = title_box[2] - title_box[0] - 2 * self.padding
        title_success, _ = self._draw_wrapped_text(
            draw,
            title,
            (title_box[0] + self.padding, title_box[1] + self.padding),
            title_width,
            title_box[3] - title_box[1] - 2 * self.padding,
            title_font,
            self.title_text_color,
            align="center",
        )

        if not title_success:
            logger.warning("Title text overflow")

        # Draw panels
        num_panels = len(panels)
        panel_width = (panels_box[2] - panels_box[0]) // num_panels
        panel_height = panels_box[3] - panels_box[1]

        sorted_panels = sorted(panels, key=lambda p: p.get("number", 999))
        for i, panel in enumerate(sorted_panels):
            panel_x = panels_box[0] + i * panel_width
            panel_y = panels_box[1]

            # Panel heading
            heading_font = self.font_helper.get_font(24, bold=True)
            heading_width = panel_width - 2 * self.padding
            heading_success, heading_height = self._draw_wrapped_text(
                draw,
                panel.get("heading", ""),
                (panel_x + self.padding, panel_y + self.padding),
                heading_width,
                100,
                heading_font,
                self.panel_heading_color,
                align="left",
            )

            # Panel description
            desc_font = self.font_helper.get_font(16)
            desc_y = panel_y + self.padding + heading_height + self.padding
            desc_height = panel_height - heading_height - 3 * self.padding
            desc_success, _ = self._draw_wrapped_text(
                draw,
                panel.get("description", ""),
                (panel_x + self.padding, desc_y),
                heading_width,
                desc_height,
                desc_font,
                self.panel_text_color,
                align="left",
            )

            if not desc_success:
                logger.warning("Panel %d description text overflow", panel.get("number", i + 1))

        # Draw summary
        summary_font = self.font_helper.get_font(18, bold=True)
        summary_width = summary_box[2] - summary_box[0] - 2 * self.padding
        summary_success, _ = self._draw_wrapped_text(
            draw,
            summary,
            (summary_box[0] + self.padding, summary_box[1] + self.padding),
            summary_width,
            summary_box[3] - summary_box[1] - 2 * self.padding,
            summary_font,
            self.summary_text_color,
            align="left",
        )

        if not summary_success:
            logger.warning("Summary text overflow")

        self.font_helper.close()
        return image
