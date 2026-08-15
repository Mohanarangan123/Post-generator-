"""
SQLAlchemy ORM model for infographic images.

Uses sqlalchemy.Uuid (dialect-agnostic) for SQLite test compatibility.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ImageStatus(str, enum.Enum):
    """Lifecycle states for a generated infographic."""
    PENDING    = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"


class ImageModel(Base):
    """ORM model for the images table."""

    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    visual_spec: Mapped[dict] = mapped_column(JSON, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=True)
    height: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ImageStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    post: Mapped["PostModel"] = relationship(  # noqa: F821
        "PostModel", back_populates="images"
    )
