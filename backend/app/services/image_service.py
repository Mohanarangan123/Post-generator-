"""
Pipeline orchestrator for infographic generation.

Coordinates: VisualSpec generation → ImageProvider → HTML template → Playwright render → DB persistence.
Never re-raises exceptions — returns ImageModel with status=FAILED on any error.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models.image import ImageModel, ImageStatus
from app.models.post import PostModel
from app.services.image_providers import get_image_provider
from app.services.image_repository import ImageRepository
from app.services.image_renderer import render_html_to_png
from app.services.image_template import ASPECT_RATIO_DIMS, build_html
from app.services.visual_spec_service import generate_visual_spec

logger = logging.getLogger(__name__)


async def run_pipeline(post_id: UUID, db: Session) -> ImageModel:
    """
    Run the full infographic generation pipeline for a post.

    Always returns an ImageModel (status=COMPLETED or status=FAILED).
    Never re-raises exceptions.
    """
    settings = get_settings()
    repo = ImageRepository(db)

    # Load post with day_topic eagerly
    post = (
        db.query(PostModel)
        .options(joinedload(PostModel.day_topic))
        .filter(PostModel.id == post_id)
        .first()
    )
    topic = post.day_topic if post else None

    # Step 1: Create PENDING record
    image = repo.create(
        post_id=post_id,
        provider="",
        prompt="",
        visual_spec={},
    )

    try:
        # Step 2: Generate VisualSpec via Qwen3
        logger.info("Step 2: Generating VisualSpec for post %s", post_id)
        visual_spec = await generate_visual_spec(post, topic)
        logger.info("VisualSpec generated: %s", visual_spec.title)

        # Step 3: Mark GENERATING and get provider
        logger.info("Step 3: Getting image provider")
        repo.update_status(image.id, ImageStatus.GENERATING)
        provider = get_image_provider(settings)
        logger.info("Using provider: %s", type(provider).__name__)

        # Step 4: Generate background image
        logger.info("Step 4: Generating background image")
        bg_bytes = await provider.generate(visual_spec.visual_concept)
        logger.info("Background image generated: %d bytes", len(bg_bytes))

        # Step 5: Build HTML
        logger.info("Step 5: Building HTML template")
        html = build_html(visual_spec, bg_bytes)
        logger.info("HTML built: %d chars", len(html))

        # Step 6: Render PNG
        logger.info("Step 6: Rendering HTML to PNG")
        w, h = ASPECT_RATIO_DIMS[visual_spec.aspect_ratio]
        output_dir = Path(settings.image_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = int(datetime.now(timezone.utc).timestamp())
        output_path = output_dir / f"{post_id}_{ts}.png"
        logger.info("Rendering to %s (%dx%d)", output_path, w, h)
        await render_html_to_png(html, output_path, w, h)
        logger.info("PNG rendered successfully")

        # Step 7: Mark COMPLETED with all metadata
        image = repo.update_status(
            image.id,
            ImageStatus.COMPLETED,
            file_path=str(output_path),
            width=w,
            height=h,
            visual_spec=visual_spec.model_dump(),
        )
        # Also set provider name and prompt on the record
        image.provider = type(provider).__name__
        image.prompt = visual_spec.visual_concept
        db.commit()
        db.refresh(image)
        logger.info("Pipeline completed for post %s → %s", post_id, output_path)

    except Exception as exc:
        logger.error("Pipeline failed for post %s: %s", post_id, exc)
        logger.error("Full traceback:", exc_info=True)  # Add full stack trace
        try:
            repo.update_status(image.id, ImageStatus.FAILED)
            db.refresh(image)
        except Exception:
            pass  # best-effort cleanup

    return image
