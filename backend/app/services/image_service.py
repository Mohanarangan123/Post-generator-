"""
Pipeline orchestrator for infographic generation.

Coordinates: VisualSpec generation → ImageProvider → Direct PNG save → DB persistence.
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
from app.services.image_providers import (
    ImageProviderError,
    MockImageProvider,
    build_image_prompt,
    get_image_provider,
    is_valid_image_bytes,
)
from app.services.image_repository import ImageRepository
from app.services.visual_spec_service import generate_visual_spec

logger = logging.getLogger(__name__)


async def run_pipeline(post_id: UUID, db: Session) -> ImageModel:
    """
    Run the full infographic generation pipeline for a post.
    
    NEW ARCHITECTURE (Phase 4 Fix):
    1. Generate VisualSpec via Ollama/Qwen3
    2. Build complete infographic prompt from VisualSpec
    3. Generate COMPLETE INFOGRAPHIC directly via image provider (Qwen-Image-2512 or mock)
    4. Save the generated PNG directly to disk
    5. Update database with metadata
    
    NO HTML TEMPLATE RENDERING - the image provider generates the complete infographic.

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
        provider = None
        try:
            provider = get_image_provider(settings)
        except ImageProviderError:
            logger.warning("Configured image provider unavailable; falling back to MockImageProvider.")
            provider = MockImageProvider()
        logger.info("Using provider: %s", type(provider).__name__)

        # Step 4: Build complete infographic prompt
        logger.info("Step 4: Building complete infographic prompt")
        image_prompt = build_image_prompt(visual_spec)
        logger.info("Prompt built: %d chars", len(image_prompt))

        # Step 5: Generate COMPLETE INFOGRAPHIC directly from provider
        logger.info("Step 5: Generating complete infographic from provider")
        try:
            image_bytes = await provider.generate(image_prompt)
            
            # Validate the generated image
            if not image_bytes or not is_valid_image_bytes(image_bytes):
                raise ImageProviderError("Provider returned invalid or empty image data")
            
            logger.info("Complete infographic generated: %d bytes", len(image_bytes))
        except Exception as exc:
            logger.warning("Provider failed; using deterministic fallback: %s", exc)
            provider = MockImageProvider()
            image_bytes = await provider.generate(image_prompt)
            logger.info("Fallback infographic generated: %d bytes", len(image_bytes))

        # Step 6: Determine output dimensions from aspect ratio
        aspect_ratio_dims = {
            "1:1": (1600, 1600),
            "4:5": (1600, 2000),
            "16:9": (1600, 900),
        }
        w, h = aspect_ratio_dims.get(visual_spec.aspect_ratio, (1600, 900))

        # Step 7: Save PNG directly to disk
        logger.info("Step 6: Saving PNG to disk")
        output_dir = Path(settings.image_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = int(datetime.now(timezone.utc).timestamp())
        output_path = output_dir / f"{post_id}_{ts}.png"
        
        # Write the image bytes directly to file
        output_path.write_bytes(image_bytes)
        logger.info("PNG saved successfully: %s", output_path)

        # Step 8: Mark COMPLETED with all metadata
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
        image.prompt = image_prompt
        db.commit()
        db.refresh(image)
        logger.info("Pipeline completed for post %s → %s", post_id, output_path)

    except Exception as exc:
        logger.error("Pipeline failed for post %s: %s", post_id, exc)
        logger.error("Full traceback:", exc_info=True)
        try:
            repo.update_status(image.id, ImageStatus.FAILED)
            db.refresh(image)
        except Exception:
            pass  # best-effort cleanup

    return image
