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


@router.get("/file/{image_id}")
async def serve_image_file(
    image_id: UUID, db: Session = Depends(get_db)
):
    """Serve the actual image file for viewing/downloading."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    from app.core.config import get_settings
    from app.models.image import ImageModel, ImageStatus
    
    image = db.query(ImageModel).filter(ImageModel.id == image_id).first()
    
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    
    if image.status != ImageStatus.COMPLETED:
        raise HTTPException(
            status_code=400, 
            detail=f"Image is not ready (status: {image.status})"
        )
    
    if not image.file_path:
        raise HTTPException(status_code=404, detail="Image file path not set")
    
    # Convert relative path to absolute if needed
    settings = get_settings()
    file_path = Path(image.file_path)
    
    if not file_path.is_absolute():
        # Resolve relative to project root (parent of backend/)
        project_root = Path(__file__).parent.parent.parent.parent
        file_path = project_root / file_path
    
    if not file_path.exists():
        logger.error(f"Image file not found: {file_path}")
        raise HTTPException(status_code=404, detail="Image file not found on disk")
    
    return FileResponse(
        path=str(file_path),
        media_type="image/png",
        filename=f"infographic_{image.post_id}.png"
    )
