"""
Images API endpoints for infographic generation.

- POST /api/images/generate/{post_id} -> generate infographic for a post
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.image import ImageStatus
from app.models.post import PostModel
from app.schemas.image import ImageRead, ImageResponse
from app.services.image_service import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/images", tags=["images"])


@router.post("/generate/{post_id}", response_model=ImageResponse)
async def generate_infographic(
    post_id: UUID, db: Session = Depends(get_db)
) -> ImageResponse:
    """Generate an infographic for a specific post."""
    post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if post is None:
        raise HTTPException(
            status_code=404, detail=f"Post {post_id} not found."
        )
    
    image = await run_pipeline(post_id, db)
    
    return ImageResponse(
        success=(image.status == ImageStatus.COMPLETED),
        **ImageRead.model_validate(image).model_dump()
    )
