"""
Infographic generation service.

Orchestrates:
1. Extract post content and build InfographicSpec
2. Load reference images (if available)
3. Call Cloudflare Flux to generate illustrated background
4. Compose final text using Pillow
5. Save and persist result to database
"""
import hashlib
import io
import logging
import re
from pathlib import Path
from typing import Optional
from uuid import UUID

from PIL import Image

from app.core.config import get_settings
from app.models.infographic import InfographicStatus
from app.models.post import PostModel
from app.schemas.infographic import InfographicPanel, InfographicSpec
from app.services.cloudflare_provider import CloudflareWorkersAIProvider
from app.services.infographic_renderer import InfographicRenderer
from app.services.infographic_repository import InfographicGenerationRepository
from app.services.post_repository import PostRepository

logger = logging.getLogger(__name__)


class InfographicSpecBuilder:
    """Builds InfographicSpec from post content."""

    @staticmethod
    def extract_lines(text: str, limit: int = 5) -> list[str]:
        """Extract non-empty lines from text, up to limit."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        return lines[:limit]

    @staticmethod
    def truncate_text(text: str, max_chars: int) -> str:
        """Truncate text to max_chars, ensuring word boundaries."""
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars].rsplit(" ", 1)[0]
        return truncated.rstrip(".,;:!")

    @staticmethod
    def _normalise_section_name(name: str) -> str:
        """Normalise generated headings so small wording changes still match."""
        name = name.lower().strip()
        name = re.sub(r"[*_`]", "", name)
        name = name.replace("–", "-").replace("—", "-")
        name = re.sub(r"^(?:a|an|the)\s+", "", name)
        return re.sub(r"\s+", " ", name)

    @staticmethod
    def _clean_section_text(text: str, *, first_line_only: bool = False) -> str:
        """Remove social-post tail content and flatten text for the canvas."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned: list[str] = []
        for line in lines:
            if line.startswith("#") or line.startswith("❓"):
                break
            cleaned.append(line)
            if first_line_only:
                break

        value = " ".join(cleaned)
        value = re.sub(r"^\s*\d+[.)]\s*", "", value)
        return re.sub(r"\s+", " ", value).strip()

    @classmethod
    def build_from_post(
        cls,
        post: PostModel,
        num_panels: int = 3,
        theme: str = "blue_navy",
        accent_color: str = "cyan",
    ) -> InfographicSpec:
        """
        Build InfographicSpec from post content.

        Extracts title, sections, and summary from LinkedIn post content.
        Assumes post content follows Phase 3 format:

        DAY N: Title
        [Hook line]
        ✅ A simple explanation: [text]
        ✅ A real-world example: [text]
        ✅ How it works: [text]
        ✅ Why it matters: [text]
        💡 Key takeaway: [text]
        [Question]
        [Hashtags]

        Args:
            post: PostModel instance with generated content
            num_panels: 3 or 4 (default 3)
            theme: Visual theme name
            accent_color: Accent color name

        Returns:
            InfographicSpec instance

        Raises:
            ValueError: If content cannot be parsed into a valid spec
        """
        if not post.content:
            raise ValueError("Post content is empty")

        content = post.content.strip()

        # Extract title (first line or "DAY N: Topic")
        first_line = content.split("\n")[0].strip()
        if first_line.lower().startswith("day"):
            # Extract title after "DAY N: "
            title_match = re.search(r"DAY\s+\d+:\s+(.+)", first_line, re.IGNORECASE)
            title = title_match.group(1) if title_match else first_line
        else:
            title = first_line

        title = cls.truncate_text(title, 90)

        # Extract sections using emoji markers
        sections = {}
        for marker in ["✅", "💡", "❓"]:
            pattern = re.escape(marker) + r"\s+(.+?):\s*(.+?)(?=✅|💡|❓|$)"
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for section_name, section_text in matches:
                section_name = cls._normalise_section_name(section_name)
                section_text = section_text.strip()
                sections[section_name] = section_text

        # Build panels based on sections
        panel_sources = [
            ("simple explanation", "Understanding the Basics"),
            ("real-world example", "Real-World Application"),
            ("how it works", "How It Works"),
            ("why it matters", "Business Impact"),
        ]

        panels = []
        for i in range(min(num_panels, len(panel_sources))):
            source_key, default_heading = panel_sources[i]
            panel_text = sections.get(source_key, f"See {default_heading} in the full post")

            # Keep useful numbered/abbreviated content. Splitting on every period
            # previously reduced values such as "1. First step" to just "1.".
            description = cls._clean_section_text(panel_text)
            description = cls.truncate_text(description, 180)

            panel = InfographicPanel(
                number=i + 1,
                heading=default_heading[:45],
                description=description,
                visual_prompt=f"Professional illustration for: {default_heading}. Educational style, no text.",
                icon_hint=None,
            )
            panels.append(panel)

        # Extract summary (key takeaway or last sentence)
        summary_text = sections.get("key takeaway", "")
        if not summary_text:
            summary_text = sections.get("why it matters", "")
        if not summary_text:
            # Use last paragraph
            paragraphs = content.split("\n\n")
            summary_text = paragraphs[-1] if paragraphs else ""

        summary = cls.truncate_text(
            cls._clean_section_text(summary_text, first_line_only=True), 180
        )
        if not summary:
            summary = f"Learn more about {title} in the full LinkedIn post"

        return InfographicSpec(
            title=title,
            subtitle=None,
            panels=panels,
            summary=summary,
            theme=theme,
            accent_color=accent_color,
        )


class InfographicService:
    """Orchestrates infographic generation pipeline."""

    def __init__(self):
        """Initialize service with settings and dependencies."""
        self.settings = get_settings()
        self.cloudflare_provider = CloudflareWorkersAIProvider()

        # Ensure output directory exists
        self.output_dir = Path(self.settings.infographic_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _load_reference_images(self) -> list[bytes]:
        """
        Load reference infographic images from images/ directory.

        Returns up to 4 reference images for Cloudflare Flux.

        Returns:
            List of image bytes (PNG)
        """
        images_dir = Path("images")
        if not images_dir.exists():
            logger.debug("No images/ directory found")
            return []

        reference_images = []
        for image_path in sorted(images_dir.glob("*.png"))[:4]:
            try:
                with open(image_path, "rb") as f:
                    image_data = f.read()
                    # Validate it's a PNG
                    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
                        reference_images.append(image_data)
                        logger.info("Loaded reference image: %s", image_path.name)
                    else:
                        logger.warning("Invalid PNG file: %s", image_path)
            except Exception as exc:
                logger.warning("Failed to load reference image %s: %s", image_path, exc)

        return reference_images

    def _build_flux_prompt(self, spec: InfographicSpec) -> str:
        """
        Build detailed Flux prompt from InfographicSpec.

        Instructs Flux to:
        - Create a professional 16:9 infographic background
        - Generate empty spaces for text (no text rendering)
        - Use specified theme colors
        - Include relevant illustrations and arrows

        Args:
            spec: InfographicSpec instance

        Returns:
            Detailed prompt for Cloudflare Flux
        """
        panel_descriptions = "\n".join(
            [f"Panel {p.number}: {p.visual_prompt}" for p in spec.panels]
        )

        theme_info = {
            "blue_navy": "Dark navy or deep blue technical theme",
            "light_blue": "Light blue and cyan modern theme",
            "professional_tech": "Professional grayscale with tech elements",
        }.get(spec.theme, "Professional blue theme")

        prompt = f"""Create a professional educational infographic in 16:9 landscape format.

Theme: {theme_info}
Color palette: Blue, navy, cyan, teal, white
Accent color: {spec.accent_color}

STRUCTURE:
- One cohesive full-bleed illustrated background
- Three or four visual scenes arranged in equal vertical zones
- Keep important subjects away from the top 15 percent and bottom 12 percent
- Clean visual flow from left to right
- Do not draw cards, banners, frames, labels, headings, or text placeholders

VISUAL ELEMENTS FOR PANELS:
{panel_descriptions}

STYLE:
- Professional illustrated infographic
- Flat or polished editorial illustration
- Strong visual hierarchy
- High contrast
- LinkedIn-quality composition
- Consistent artistic style across all panels

CRITICAL RESTRICTIONS:
- NO text of any kind
- NO letters or words
- NO numbers
- NO logos or watermarks
- NO signatures
- NO watermarks or random symbols
- NO UI screenshots
- NO photorealism unless explicitly needed

Generate only the supporting artwork. Deterministic cards, banners, and typography
will be added later by the application."""

        return prompt

    async def generate_infographic(
        self,
        post_id: UUID,
        db,
        generation_id: Optional[UUID] = None,
        num_panels: int = 3,
        theme: str = "blue_navy",
        accent_color: str = "cyan",
        regenerate_image: bool = True,
    ) -> tuple[bool, str, Optional[str]]:
        """
        Generate complete infographic for a post.

        Pipeline:
        1. Fetch post and build InfographicSpec
        2. Load reference images
        3. Call Cloudflare Flux for illustrated background
        4. Render text using Pillow
        5. Save PNG to output directory
        6. Update database

        Args:
            post_id: ID of post to generate infographic for
            db: Database session
            generation_id: Optional existing generation to retry
            num_panels: 3 or 4
            theme: Visual theme
            accent_color: Accent color
            regenerate_image: If False, reuse existing image (text-only recomposition)

        Returns:
            (success: bool, message: str, output_path: Optional[str])
        """
        repo = PostRepository(db)
        post = repo.get(post_id)

        if not post:
            return False, f"Post {post_id} not found", None

        gen_repo = InfographicGenerationRepository(db)

        try:
            # Build InfographicSpec
            logger.info("Building InfographicSpec for post %s", post_id)
            spec = InfographicSpecBuilder.build_from_post(
                post,
                num_panels=num_panels,
                theme=theme,
                accent_color=accent_color,
            )

            # Hash prompt for deduplication
            spec_dict = spec.model_dump()
            prompt_hash = hashlib.sha256(
                str(spec_dict).encode("utf-8")
            ).hexdigest()

            # Create or get generation record
            if generation_id:
                generation = gen_repo.get(generation_id)
                if not generation:
                    return False, f"Generation {generation_id} not found", None
            else:
                generation = gen_repo.create(
                    post_id=post_id,
                    provider="cloudflare",
                    model=self.settings.cloudflare_image_model,
                    prompt_hash=prompt_hash,
                    status=InfographicStatus.PENDING,
                    width=self.settings.cloudflare_image_width,
                    height=self.settings.cloudflare_image_height,
                )
                generation_id = generation.id

            # Update status to PROCESSING
            gen_repo.update_status(generation_id, InfographicStatus.PROCESSING)

            # Generate illustrated background
            image_bytes = None
            if regenerate_image:
                logger.info("Generating illustrated background via Cloudflare Flux")
                reference_images = self._load_reference_images()
                flux_prompt = self._build_flux_prompt(spec)

                image_bytes = await self.cloudflare_provider.generate_image(
                    flux_prompt, reference_images
                )

                logger.info("Cloudflare Flux returned %d bytes", len(image_bytes))
            else:
                # Reuse existing image
                if generation.output_path:
                    output_path = self.output_dir / generation.output_path
                    if output_path.exists():
                        with open(output_path, "rb") as f:
                            image_bytes = f.read()
                        logger.info("Reusing existing image: %s", generation.output_path)
                    else:
                        logger.warning(
                            "Existing image not found: %s", generation.output_path
                        )
                        image_bytes = None

                if not image_bytes:
                    # Fallback: generate new image
                    logger.warning("Regenerate=False but no existing image. Generating new image.")
                    reference_images = self._load_reference_images()
                    flux_prompt = self._build_flux_prompt(spec)
                    image_bytes = await self.cloudflare_provider.generate_image(
                        flux_prompt, reference_images
                    )

            # Load image from bytes
            image = Image.open(io.BytesIO(image_bytes))
            logger.info("Loaded PIL Image: %s", image.format)

            # Compose text onto image
            logger.info("Composing text onto image")
            renderer = InfographicRenderer(
                width=self.settings.cloudflare_image_width,
                height=self.settings.cloudflare_image_height,
            )

            # Prepare panel dicts for renderer
            panel_dicts = [
                {
                    "number": p.number,
                    "heading": p.heading,
                    "description": p.description,
                }
                for p in spec.panels
            ]

            composed_image = renderer.compose(
                image,
                title=spec.title,
                panels=panel_dicts,
                summary=spec.summary,
                subtitle=spec.subtitle,
            )

            # Save to file
            filename = f"{post_id}_{generation_id}.png"
            output_path = self.output_dir / filename

            # Atomic write: save to temp file first
            temp_path = output_path.with_suffix(".tmp")
            composed_image.save(temp_path, "PNG", optimize=True)
            temp_path.replace(output_path)

            logger.info("Saved infographic: %s (%d bytes)", output_path, output_path.stat().st_size)

            # Update database
            gen_repo.update_status(
                generation_id,
                InfographicStatus.COMPLETED,
                output_path=filename,
            )

            return True, "Infographic generated successfully", filename

        except Exception as exc:
            logger.error("Infographic generation failed: %s", exc, exc_info=True)

            # Update database with error
            if generation_id:
                gen_repo.update_status(
                    generation_id,
                    InfographicStatus.FAILED,
                    error_message=str(exc),
                )

            return False, f"Generation failed: {exc}", None
