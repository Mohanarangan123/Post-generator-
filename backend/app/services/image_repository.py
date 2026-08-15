"""Database CRUD operations for ImageModel."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.image import ImageModel, ImageStatus

logger = logging.getLogger(__name__)


class ImageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        post_id: UUID,
        provider: str,
        prompt: str,
        visual_spec: dict,
    ) -> ImageModel:
        image = ImageModel(
            id=uuid.uuid4(),
            post_id=post_id,
            provider=provider,
            prompt=prompt,
            visual_spec=visual_spec,
            status=ImageStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(image)
        self.db.commit()
        self.db.refresh(image)
        return image

    def update_status(
        self,
        image_id: UUID,
        status: str,
        file_path: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        visual_spec: Optional[dict] = None,
    ) -> ImageModel:
        image = self.db.query(ImageModel).filter(ImageModel.id == image_id).first()
        if image is None:
            raise ValueError(f"ImageModel {image_id} not found.")
        image.status = status
        if file_path is not None:
            image.file_path = file_path
        if width is not None:
            image.width = width
        if height is not None:
            image.height = height
        if visual_spec is not None:
            image.visual_spec = visual_spec
        self.db.commit()
        self.db.refresh(image)
        return image

    def get(self, image_id: UUID) -> Optional[ImageModel]:
        return self.db.query(ImageModel).filter(ImageModel.id == image_id).first()

    def get_by_post(self, post_id: UUID) -> Optional[ImageModel]:
        return (
            self.db.query(ImageModel)
            .filter(ImageModel.post_id == post_id)
            .order_by(ImageModel.created_at.desc())
            .first()
        )
