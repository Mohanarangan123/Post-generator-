"""
Data access layer for infographic generations.

Handles all database operations for InfographicGenerationModel.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.infographic import InfographicGenerationModel, InfographicStatus
from app.schemas.infographic import InfographicGenerationRead

logger = logging.getLogger(__name__)


class InfographicGenerationRepository:
    """Repository for InfographicGenerationModel database operations."""

    def __init__(self, db: Session):
        """Initialize with database session."""
        self.db = db

    def create(
        self,
        post_id: UUID,
        provider: str,
        model: str,
        prompt_hash: str,
        status: str = InfographicStatus.PENDING,
        width: int = 1536,
        height: int = 864,
        output_path: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> InfographicGenerationModel:
        """
        Create a new infographic generation record.

        Args:
            post_id: Related post ID
            provider: Image provider name (e.g., 'cloudflare')
            model: Model name (e.g., '@cf/black-forest-labs/flux-2-klein-9b')
            prompt_hash: SHA256 hash of the prompt
            status: Initial status (default: PENDING)
            width: Image width (default: 1536)
            height: Image height (default: 864)
            output_path: Path to generated image (optional)
            error_message: Error details if generation failed

        Returns:
            Created InfographicGenerationModel instance
        """
        generation = InfographicGenerationModel(
            post_id=post_id,
            provider=provider,
            model=model,
            prompt_hash=prompt_hash,
            status=status,
            width=width,
            height=height,
            output_path=output_path,
            error_message=error_message,
        )
        self.db.add(generation)
        self.db.commit()
        self.db.refresh(generation)
        logger.info(
            "Created infographic generation: %s for post: %s (status=%s)",
            generation.id,
            post_id,
            status,
        )
        return generation

    def get(self, generation_id: UUID) -> Optional[InfographicGenerationModel]:
        """
        Get a generation by ID.

        Args:
            generation_id: Generation ID

        Returns:
            InfographicGenerationModel or None if not found
        """
        return self.db.query(InfographicGenerationModel).filter(
            InfographicGenerationModel.id == generation_id
        ).first()

    def get_by_post(self, post_id: UUID) -> Optional[InfographicGenerationModel]:
        """
        Get the most recent generation for a post.

        Args:
            post_id: Post ID

        Returns:
            Most recent InfographicGenerationModel for the post, or None
        """
        return (
            self.db.query(InfographicGenerationModel)
            .filter(InfographicGenerationModel.post_id == post_id)
            .order_by(InfographicGenerationModel.created_at.desc())
            .first()
        )

    def list_by_post(self, post_id: UUID) -> list[InfographicGenerationModel]:
        """
        List all generations for a post (newest first).

        Args:
            post_id: Post ID

        Returns:
            List of InfographicGenerationModel
        """
        return (
            self.db.query(InfographicGenerationModel)
            .filter(InfographicGenerationModel.post_id == post_id)
            .order_by(InfographicGenerationModel.created_at.desc())
            .all()
        )

    def update_status(
        self,
        generation_id: UUID,
        status: str,
        output_path: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[InfographicGenerationModel]:
        """
        Update a generation's status.

        Args:
            generation_id: Generation ID
            status: New status (PENDING, PROCESSING, COMPLETED, FAILED)
            output_path: Path to output image (for COMPLETED)
            error_message: Error details (for FAILED)

        Returns:
            Updated InfographicGenerationModel or None if not found
        """
        generation = self.get(generation_id)
        if not generation:
            logger.warning("Generation not found: %s", generation_id)
            return None

        generation.status = status
        if output_path is not None:
            generation.output_path = output_path
        if error_message is not None:
            generation.error_message = error_message

        if status == InfographicStatus.COMPLETED:
            generation.completed_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(generation)

        logger.info(
            "Updated generation %s: status=%s, output_path=%s",
            generation_id,
            status,
            output_path,
        )
        return generation

    def get_failed(self) -> list[InfographicGenerationModel]:
        """
        Get all failed generations (for retry).

        Returns:
            List of failed InfographicGenerationModel
        """
        return (
            self.db.query(InfographicGenerationModel)
            .filter(InfographicGenerationModel.status == InfographicStatus.FAILED)
            .order_by(InfographicGenerationModel.created_at.asc())
            .all()
        )

    def get_pending_or_processing(self) -> list[InfographicGenerationModel]:
        """
        Get all pending or processing generations.

        Returns:
            List of pending/processing InfographicGenerationModel
        """
        return (
            self.db.query(InfographicGenerationModel)
            .filter(
                InfographicGenerationModel.status.in_(
                    [InfographicStatus.PENDING, InfographicStatus.PROCESSING]
                )
            )
            .order_by(InfographicGenerationModel.created_at.asc())
            .all()
        )

    def to_read_schema(
        self, generation: InfographicGenerationModel
    ) -> InfographicGenerationRead:
        """
        Convert ORM model to read schema.

        Args:
            generation: InfographicGenerationModel instance

        Returns:
            InfographicGenerationRead schema
        """
        return InfographicGenerationRead(
            id=generation.id,
            post_id=generation.post_id,
            provider=generation.provider,
            model=generation.model,
            status=generation.status,
            width=generation.width,
            height=generation.height,
            prompt_hash=generation.prompt_hash,
            output_path=generation.output_path,
            error_message=generation.error_message,
            created_at=generation.created_at.isoformat(),
            completed_at=generation.completed_at.isoformat()
            if generation.completed_at
            else None,
        )
