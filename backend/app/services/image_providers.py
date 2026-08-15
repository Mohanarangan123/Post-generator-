"""
Pluggable image provider interface.

ImageProvider (ABC)
├── MockImageProvider    — deterministic local PNG, no network
├── LocalSVGIllustrationProvider — local editor-friendly vector fallback
└── HuggingFaceImageProvider — HF Inference API (cloud)
"""
import io
import logging
from abc import ABC, abstractmethod

import httpx
from PIL import Image, ImageDraw

from app.schemas.image import VisualSpec

logger = logging.getLogger(__name__)

HF_TIMEOUT_SECONDS = 60.0


class ImageProviderError(Exception):
    """Raised when an image provider fails to generate an image."""


class ImageProvider(ABC):
    """Abstract base class for all image providers."""

    @abstractmethod
    async def generate(self, prompt: str) -> bytes:
        """Generate an illustration asset for the given prompt. Returns PNG or SVG bytes."""


def render_svg_fallback(spec: VisualSpec | None = None, *, prompt: str | None = None) -> bytes:
    """Create a deterministic SVG illustration without network access."""
    title = (spec.title if spec else "Workflow")
    concept = (spec.visual_concept if spec else prompt or "workflow")
    title_lower = f"{title} {concept}".lower()
    if "python" in title_lower:
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><rect width="420" height="420" rx="26" fill="#F0F9FF"/><circle cx="312" cy="96" r="48" fill="#DBEAFE"/><rect x="84" y="118" width="208" height="170" rx="20" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><rect x="108" y="150" width="160" height="92" rx="12" fill="#EAF3FF"/><path d="M118 188h140" stroke="#1D4ED8" stroke-width="10" stroke-linecap="round"/><path d="M118 216h90" stroke="#93C5FD" stroke-width="8" stroke-linecap="round"/><circle cx="310" cy="246" r="48" fill="#FFFFFF" stroke="#1D4ED8" stroke-width="4"/><path d="M292 246c0-16 13-29 29-29 17 0 30 13 30 29 0 17-13 30-30 30-16 0-29-13-29-30zm18 0v-10h22v10h-8v18h-3v-18h-9z" fill="#1D4ED8"/><path d="M118 328h170" stroke="#93C5FD" stroke-width="8" stroke-linecap="round"/></svg>'''
    elif "database" in title_lower or "sql" in title_lower:
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><rect width="420" height="420" rx="26" fill="#F0F9FF"/><ellipse cx="150" cy="114" rx="88" ry="28" fill="#DBEAFE"/><rect x="62" y="114" width="176" height="104" rx="12" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><ellipse cx="150" cy="214" rx="88" ry="28" fill="#DBEAFE"/><rect x="62" y="214" width="176" height="104" rx="12" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><path d="M62 114v104M238 114v104M62 214v104M238 214v104" stroke="#93C5FD" stroke-width="4"/><path d="M278 118h52v208h-52" fill="#FFFFFF" stroke="#60A5FA" stroke-width="4"/><path d="M282 148h48M282 186h48M282 224h48" stroke="#60A5FA" stroke-width="5" stroke-linecap="round"/><path d="M278 292l30 28 48-60" fill="none" stroke="#1D4ED8" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>'''
    elif "ai" in title_lower or "ml" in title_lower or "model" in title_lower:
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><rect width="420" height="420" rx="26" fill="#F0F9FF"/><circle cx="135" cy="160" r="40" fill="#DBEAFE"/><circle cx="230" cy="122" r="36" fill="#DBEAFE"/><circle cx="280" cy="220" r="42" fill="#DBEAFE"/><circle cx="150" cy="275" r="34" fill="#DBEAFE"/><path d="M132 160l94-40 48 96-92 52-60-42" fill="none" stroke="#1D4ED8" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/><path d="M160 270l72-56" stroke="#1D4ED8" stroke-width="8" stroke-linecap="round"/><rect x="58" y="304" width="132" height="56" rx="16" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><rect x="228" y="310" width="136" height="52" rx="16" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><path d="M88 335h70M246 335h96" stroke="#60A5FA" stroke-width="7" stroke-linecap="round"/></svg>'''
    elif "api" in title_lower or "server" in title_lower:
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><rect width="420" height="420" rx="26" fill="#F0F9FF"/><rect x="68" y="120" width="122" height="170" rx="18" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><rect x="230" y="120" width="122" height="170" rx="18" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><rect x="108" y="158" width="42" height="42" rx="8" fill="#DBEAFE"/><rect x="270" y="168" width="42" height="42" rx="8" fill="#DBEAFE"/><path d="M190 205h40" stroke="#1D4ED8" stroke-width="8" stroke-linecap="round"/><path d="M214 205l-18 18M214 205l-18-18" stroke="#1D4ED8" stroke-width="8" stroke-linecap="round"/><rect x="110" y="248" width="70" height="16" rx="8" fill="#93C5FD"/><rect x="242" y="250" width="70" height="16" rx="8" fill="#93C5FD"/><circle cx="155" cy="316" r="20" fill="#FFFFFF" stroke="#60A5FA" stroke-width="4"/><circle cx="265" cy="316" r="20" fill="#FFFFFF" stroke="#60A5FA" stroke-width="4"/></svg>'''
    else:
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 420"><rect width="420" height="420" rx="26" fill="#F0F9FF"/><rect x="52" y="96" width="104" height="82" rx="16" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><rect x="158" y="155" width="104" height="82" rx="16" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><rect x="264" y="96" width="104" height="82" rx="16" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><rect x="158" y="245" width="104" height="82" rx="16" fill="#FFFFFF" stroke="#BFDBFE" stroke-width="4"/><path d="M156 197h2M119 178l39 18M262 178l-40 18M208 237v8M158 287h104" stroke="#1D4ED8" stroke-width="8" stroke-linecap="round"/><path d="M92 146h24M87 180h28M194 195h28M300 146h20M300 180h26M194 291h28" stroke="#60A5FA" stroke-width="6" stroke-linecap="round"/></svg>'''
    return svg.encode("utf-8")


def is_valid_image_bytes(payload: bytes) -> bool:
    """Validate an illustration payload: PNG/JPEG/WebP or SVG is acceptable."""
    if not payload:
        return False
    text = payload.lstrip()
    if text.startswith(b"<svg") or text.startswith(b"<?xml"):
        return True
    try:
        with Image.open(io.BytesIO(payload)) as image:
            width, height = image.size
            return width > 0 and height > 0
    except Exception:
        return False


async def load_image(provider: ImageProvider, prompt: str, spec: VisualSpec | None = None) -> bytes:
    """Try provider output, validate it, and fall back deterministically if it fails."""
    try:
        payload = await provider.generate(prompt)
        if not payload:
            raise ImageProviderError("provider returned empty image bytes")
        if is_valid_image_bytes(payload):
            return payload
        raise ImageProviderError("provider returned invalid image data")
    except Exception as exc:
        logger.warning("Illustration provider failed; using deterministic SVG fallback: %s", exc)
        if spec is not None:
            return render_svg_fallback(spec)
        return render_svg_fallback(prompt=prompt)


def build_image_prompt(spec: VisualSpec) -> str:
    """Create a dedicated illustration-generation prompt from the infographic specification."""
    node_summary = ", ".join(
        f"{node.step}. {node.title}"
        for node in spec.diagram_nodes
    )
    return (
        "Create a clean professional editorial illustration for an educational LinkedIn infographic.\n\n"
        f"Topic: {spec.title}\n\n"
        f"Visual concept:\n{spec.visual_concept}\n\n"
        "Create a modern technology education illustration showing the main concept visually.\n\n"
        "Style:\n"
        "- professional LinkedIn educational infographic\n"
        "- clean modern vector/editorial illustration\n"
        "- polished corporate technology aesthetic\n"
        "- clear visual hierarchy\n"
        "- blue, white and subtle accent colors\n"
        "- friendly but professional\n"
        "- realistic proportions\n"
        "- simple uncluttered composition\n"
        "- suitable for a technical audience\n"
        "- high visual clarity\n\n"
        "Show:\n"
        f"{node_summary}\n\n"
        "Do NOT render any text, captions, labels, numbers, logos, paragraphs, UI text or typography inside the image.\n"
        "The application will add all text separately.\n\n"
        "16:9 or suitable wide infographic composition."
    )


class MockImageProvider(ImageProvider):
    """Deterministic local mock provider that renders an abstract illustration asset."""

    async def generate(self, prompt: str) -> bytes:
        if not prompt:
            raise ValueError("prompt must not be empty")

        width, height = 1200, 675
        image = Image.new("RGB", (width, height), color=(240, 246, 255))
        draw = ImageDraw.Draw(image)

        for y in range(height):
            ratio = y / max(1, height)
            r = int(228 + 18 * ratio)
            g = int(240 + 10 * ratio)
            b = int(255)
            draw.line((0, y, width, y), fill=(r, g, b))

        draw.ellipse((120, 170, 420, 470), fill=(255, 255, 255), outline=(178, 208, 255), width=6)
        draw.rounded_rectangle((500, 170, 980, 510), radius=34, fill=(255, 255, 255), outline=(157, 177, 231), width=5)
        draw.rectangle((710, 250, 850, 350), fill=(79, 140, 255))
        draw.polygon([(500, 170), (610, 170), (560, 110)], fill=(255, 255, 255))
        draw.rounded_rectangle((210, 510, 980, 560), radius=20, fill=(15, 76, 150))

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()


class LocalSVGIllustrationProvider(ImageProvider):
    """Returns a deterministic local vector illustration asset."""

    async def generate(self, prompt: str) -> bytes:
        if not prompt:
            raise ValueError("prompt must not be empty")
        return render_svg_fallback(prompt=prompt)


class HuggingFaceImageProvider(ImageProvider):
    """Calls the Hugging Face Inference API to generate a technical illustration."""

    def __init__(self, token: str, model_id: str) -> None:
        self._token = token
        self._model_id = model_id

    async def generate(self, prompt: str) -> bytes:
        if not self._token:
            raise ImageProviderError(
                "HF_TOKEN must be configured to use HuggingFaceImageProvider."
            )
        if not self._model_id:
            raise ImageProviderError(
                "HF_IMAGE_MODEL must be configured to use HuggingFaceImageProvider."
            )
        url = f"https://api-inference.huggingface.co/models/{self._model_id}"
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with httpx.AsyncClient(timeout=HF_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json={"inputs": prompt}, headers=headers)
        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                f"Hugging Face Inference API request timed out after {HF_TIMEOUT_SECONDS}s."
            ) from exc
        except httpx.HTTPError as exc:
            raise ImageProviderError(f"Hugging Face request failed: {exc}") from exc

        if response.status_code >= 300:
            detail = response.text[:250]
            raise ImageProviderError(
                f"Hugging Face Inference API returned status {response.status_code}: {detail}"
            )

        content_type = response.headers.get("content-type", "")
        if "image" not in content_type and not response.content.startswith(b"\x89PNG") and not response.content.lstrip().startswith(b"<svg"):
            raise ImageProviderError(
                f"Hugging Face Inference API returned non-image content: {content_type}"
            )
        return response.content


def get_image_provider(settings) -> ImageProvider:
    """Factory: return the appropriate provider based on settings."""
    if str(settings.image_provider).lower() in {"huggingface", "hf"}:
        if not getattr(settings, "hf_token", ""):
            raise ImageProviderError(
                "HF_TOKEN must be configured when IMAGE_PROVIDER=huggingface."
            )
        model_id = getattr(settings, "hf_image_model", "") or "black-forest-labs/FLUX.1-dev"
        return HuggingFaceImageProvider(settings.hf_token, model_id)
    if str(settings.image_provider).lower() in {"svg", "local_svg", "local"}:
        return LocalSVGIllustrationProvider()
    return MockImageProvider()
