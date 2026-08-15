"""HTML/CSS template for infographic rendering."""
import base64
import logging

from app.schemas.image import VisualSpec

logger = logging.getLogger(__name__)

ASPECT_RATIO_DIMS: dict[str, tuple[int, int]] = {
    "1:1":  (1080, 1080),
    "4:5":  (1080, 1350),
    "16:9": (1920, 1080),
}


def _get_style_css(style: str, w: int, h: int) -> str:
    """Return CSS string for the given style variant."""
    if style == "dark-tech":
        bg = "background: #0a0a1a"
        fg = "color: #e0e0ff"
    elif style == "light-minimal":
        bg = "background: #ffffff"
        fg = "color: #1a1a1a"
    else:  # blue-gradient
        bg = "background: linear-gradient(135deg, #1e3a5f, #4a90d9)"
        fg = "color: #ffffff"

    return f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    width: {w}px;
    height: {h}px;
    overflow: hidden;
    font-family: 'Segoe UI', Arial, sans-serif;
    {bg};
    {fg};
}}
.container {{
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 48px 56px;
    gap: 20px;
}}
.day-header {{
    font-size: 22px;
    font-weight: 700;
    letter-spacing: 4px;
    text-transform: uppercase;
    opacity: 0.75;
}}
.title {{
    font-size: 40px;
    font-weight: 800;
    line-height: 1.2;
}}
.visual-area {{
    flex: 1;
    overflow: hidden;
    border-radius: 12px;
}}
.visual-area img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 12px;
}}
.key-points {{
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 8px;
}}
.key-points li {{
    font-size: 18px;
    line-height: 1.4;
    padding-left: 20px;
    position: relative;
}}
.key-points li::before {{
    content: "▸";
    position: absolute;
    left: 0;
}}
.footer {{
    font-size: 14px;
    opacity: 0.6;
    text-align: center;
    letter-spacing: 2px;
}}
"""


def build_html(visual_spec: VisualSpec, bg_bytes: bytes) -> str:
    """
    Build a self-contained HTML infographic document.

    Args:
        visual_spec: The structured visual specification from Qwen3.
        bg_bytes: Raw PNG bytes for the background image (may be empty).

    Returns:
        Complete <!DOCTYPE html> string ready for Playwright rendering.
    """
    w, h = ASPECT_RATIO_DIMS[visual_spec.aspect_ratio]
    bg_b64 = base64.b64encode(bg_bytes).decode() if bg_bytes else ""
    key_points_li = "\n".join(
        f"    <li>{point}</li>" for point in visual_spec.key_points
    )
    style_css = _get_style_css(visual_spec.style, w, h)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <style>{style_css}</style>
</head>
<body>
  <div class="container">
    <div class="day-header">DAY {visual_spec.day_number:02d}</div>
    <h1 class="title">{visual_spec.title}</h1>
    <div class="visual-area">
      <img src="data:image/png;base64,{bg_b64}" alt="visual background" />
    </div>
    <ul class="key-points">
{key_points_li}
    </ul>
    <div class="footer">#LearnWithAI</div>
  </div>
</body>
</html>"""
