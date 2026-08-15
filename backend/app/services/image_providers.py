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
    """
    Create a complete infographic generation prompt from the VisualSpec.
    
    This prompt instructs the model to generate a FINISHED INFOGRAPHIC, not just
    a decorative background or illustration asset.
    """
    # Build node descriptions
    node_descriptions = []
    for node in spec.diagram_nodes:
        node_descriptions.append(f"  Scene {node.step}: {node.title}")
        if node.description:
            node_descriptions.append(f"    {node.description}")
    nodes_text = "\n".join(node_descriptions)
    
    # Build key points
    key_points_text = "\n".join(f"  • {point}" for point in spec.key_points)
    
    return f"""Create a complete finished educational infographic for professional social media.

INFOGRAPHIC CONTENT:

Title: {spec.title}
Subtitle: {spec.subtitle}
Day Number: {spec.day_number}
Category: {spec.diagram_type.upper()}

Visual Concept:
{spec.visual_concept}

Content Structure (3-5 connected visual sections):
{nodes_text}

Key Takeaways:
{key_points_text}

CRITICAL REQUIREMENTS:

DO:
✓ Create a COMPLETE FINISHED INFOGRAPHIC as a single cohesive composition
✓ Generate the ENTIRE image including all text, headings, labels, and typography
✓ Use illustrated human characters interacting with the subject
✓ Include objects: documents, computers, books, diagrams, icons
✓ Show arrows and visual connectors demonstrating flow and progression
✓ Organize information into 3-5 visually connected scenes/sections
✓ Include concise readable headings and explanatory labels
✓ Display the day number (Day {spec.day_number:02d}) prominently
✓ Show the title "{spec.title}" as the main heading
✓ Add short text labels where appropriate to explain concepts
✓ Create a clear visual hierarchy with proper typography
✓ Use a professional editorial illustration style
✓ Apply a clean light background
✓ Use blue/cyan dominant color palette with white accents
✓ Make it visually rich and informative
✓ Ensure it looks like a professionally designed educational infographic

DO NOT:
✗ Create empty rectangular boxes or placeholder panels
✗ Generate UI cards, dashboard layouts, or presentation slides
✗ Make generic decorative backgrounds
✗ Create fake browser windows or application interfaces
✗ Produce template-like structures
✗ Leave blank spaces that need to be filled later
✗ Create photorealistic people (use illustrated characters)
✗ Add random decorative elements unrelated to the content

VISUAL STYLE:
- Professional editorial/explainer infographic style
- Multiple illustrated scenes arranged cohesively
- Educational technology publication aesthetic
- Clear hierarchy and visual flow
- Human characters when relevant to the topic
- Objects and diagrams supporting the narrative
- Arrows showing concept progression
- Short readable text integrated naturally
- Light background with blue/cyan dominance
- Clean professional composition
- Looks like it belongs in a tech blog or professional learning platform

OUTPUT FORMAT:
- Complete infographic ready for social media
- {spec.aspect_ratio} aspect ratio
- All text, graphics, and elements included
- No post-processing needed
- Professional publication quality

The result should be a complete, polished educational infographic that communicates the entire concept visually and textually, similar to what you'd find in a professional technology publication or LinkedIn educational post."""


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
    """Calls the Hugging Face Inference API to generate a complete infographic."""

    def __init__(self, token: str, model_id: str, provider: str = "") -> None:
        self._token = token
        self._model_id = model_id
        self._provider = provider

    async def generate(self, prompt: str) -> bytes:
        if not self._token:
            raise ImageProviderError(
                "HF_TOKEN must be configured to use HuggingFaceImageProvider."
            )
        if not self._model_id:
            raise ImageProviderError(
                "HF_IMAGE_MODEL must be configured to use HuggingFaceImageProvider."
            )
        
        # Build URL based on provider
        if self._provider:
            url = f"https://api-inference.huggingface.co/models/{self._model_id}"
            headers = {
                "Authorization": f"Bearer {self._token}",
                "x-use-inference-provider": self._provider,
            }
        else:
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
        model_id = getattr(settings, "hf_image_model", "") or "Qwen/Qwen-Image-2512"
        provider = getattr(settings, "hf_inference_provider", "")
        return HuggingFaceImageProvider(settings.hf_token, model_id, provider)
    if str(settings.image_provider).lower() in {"svg", "local_svg", "local"}:
        return LocalSVGIllustrationProvider()
    return MockImageProvider()
