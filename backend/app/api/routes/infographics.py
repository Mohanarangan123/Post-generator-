"""
FastAPI endpoints for Phase 4: Infographic Generation.

- POST   /api/posts/{post_id}/infographic         -> Create generation job
- GET    /api/infographics/{generation_id}        -> Get generation status
- GET    /api/infographics/{generation_id}/image  -> Download PNG image
- POST   /api/infographics/{generation_id}/retry  -> Retry failed generation
"""
import logging
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.post import PostModel
from app.schemas.infographic import (
    InfographicGenerationResponse,
    InfographicRetryRequest,
)
from app.services.infographic_repository import InfographicGenerationRepository
from app.services.infographic_service import InfographicService
from app.services.post_repository import PostRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["infographics"])


@router.post("/posts/{post_id}/infographic", response_model=InfographicGenerationResponse)
async def create_infographic(
    post_id: UUID,
    num_panels: int = 3,
    theme: str = "blue_navy",
    accent_color: str = "cyan",
    db: Session = Depends(get_db),
) -> InfographicGenerationResponse:
    """
    Create an infographic generation job for a post.

    Args:
        post_id: ID of the post to generate infographic for
        num_panels: Number of panels (3 or 4, default 3)
        theme: Visual theme (blue_navy, light_blue, professional_tech)
        accent_color: Accent color (cyan, teal, white, navy)
        db: Database session

    Returns:
        InfographicGenerationResponse with generation ID and status
    """
    # Validate post exists
    post_repo = PostRepository(db)
    post = post_repo.get(post_id)

    if not post:
        raise HTTPException(
            status_code=404, detail=f"Post {post_id} not found."
        )

    if not post.content:
        raise HTTPException(
            status_code=400, detail="Post content is empty. Generate content first."
        )

    # Validate parameters
    if num_panels not in (3, 4):
        raise HTTPException(
            status_code=400, detail="num_panels must be 3 or 4"
        )

    if theme not in ("blue_navy", "light_blue", "professional_tech"):
        raise HTTPException(
            status_code=400, detail="Invalid theme"
        )

    # Generate infographic
    service = InfographicService()
    try:
        success, message, output_path = await service.generate_infographic(
            post_id=post_id,
            db=db,
            num_panels=num_panels,
            theme=theme,
            accent_color=accent_color,
            regenerate_image=True,
        )

        if success:
            # Fetch the generation record
            gen_repo = InfographicGenerationRepository(db)
            # Get most recent generation for post
            generation = gen_repo.get_by_post(post_id)

            if generation:
                image_url = f"/api/infographics/{generation.id}/image"
                return InfographicGenerationResponse(
                    success=True,
                    message=message,
                    generation=gen_repo.to_read_schema(generation),
                    image_url=image_url,
                )

        return InfographicGenerationResponse(
            success=False,
            message=message,
            generation=None,
            image_url=None,
        )

    except Exception as exc:
        logger.error(
            "Failed to create infographic for post %s: %s", post_id, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Generation failed: {exc}"
        )


@router.get("/infographics/{generation_id}", response_model=InfographicGenerationResponse)
def get_infographic_status(
    generation_id: UUID, db: Session = Depends(get_db)
) -> InfographicGenerationResponse:
    """
    Get the status of an infographic generation.

    Args:
        generation_id: ID of the generation
        db: Database session

    Returns:
        InfographicGenerationResponse with current status
    """
    gen_repo = InfographicGenerationRepository(db)
    generation = gen_repo.get(generation_id)

    if not generation:
        raise HTTPException(
            status_code=404, detail=f"Generation {generation_id} not found."
        )

    image_url = None
    if generation.output_path:
        image_url = f"/api/infographics/{generation_id}/image"

    return InfographicGenerationResponse(
        success=True,
        message=f"Status: {generation.status}",
        generation=gen_repo.to_read_schema(generation),
        image_url=image_url,
    )


@router.get("/infographics/{generation_id}/image")
def get_infographic_image(
    generation_id: UUID, db: Session = Depends(get_db)
) -> FileResponse:
    """
    Download the generated infographic PNG image.

    Args:
        generation_id: ID of the generation
        db: Database session

    Returns:
        PNG image file
    """
    gen_repo = InfographicGenerationRepository(db)
    generation = gen_repo.get(generation_id)

    if not generation:
        raise HTTPException(
            status_code=404, detail=f"Generation {generation_id} not found."
        )

    if not generation.output_path:
        raise HTTPException(
            status_code=404, detail="Image not available (generation may still be processing)"
        )

    settings = get_settings()
    image_path = Path(settings.infographic_output_dir) / generation.output_path

    if not image_path.exists():
        logger.error("Image file not found: %s", image_path)
        raise HTTPException(
            status_code=404, detail="Image file not found on server"
        )

    return FileResponse(
        image_path,
        media_type="image/png",
        filename=f"infographic_{generation_id}.png",
    )


@router.post("/infographics/{generation_id}/retry", response_model=InfographicGenerationResponse)
async def retry_infographic_generation(
    generation_id: UUID,
    body: InfographicRetryRequest,
    db: Session = Depends(get_db),
) -> InfographicGenerationResponse:
    """
    Retry a failed infographic generation.

    Args:
        generation_id: ID of the generation to retry
        body: Request body with regenerate_image flag
        db: Database session

    Returns:
        InfographicGenerationResponse with new status
    """
    gen_repo = InfographicGenerationRepository(db)
    generation = gen_repo.get(generation_id)

    if not generation:
        raise HTTPException(
            status_code=404, detail=f"Generation {generation_id} not found."
        )

    if generation.status not in ("FAILED", "COMPLETED"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Can only regenerate completed or retry failed generations. "
                f"Current status: {generation.status}"
            ),
        )

    # Retry generation
    service = InfographicService()
    try:
        success, message, output_path = await service.generate_infographic(
            post_id=generation.post_id,
            db=db,
            generation_id=generation_id,
            regenerate_image=body.regenerate_image,
        )

        # Fetch updated generation record
        updated_generation = gen_repo.get(generation_id)

        image_url = None
        if updated_generation and updated_generation.output_path:
            image_url = f"/api/infographics/{generation_id}/image"

        return InfographicGenerationResponse(
            success=success,
            message=message,
            generation=gen_repo.to_read_schema(updated_generation) if updated_generation else None,
            image_url=image_url,
        )

    except Exception as exc:
        logger.error(
            "Retry failed for generation %s: %s", generation_id, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500, detail=f"Retry failed: {exc}"
        )
