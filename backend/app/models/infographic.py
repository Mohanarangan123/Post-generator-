"""
SQLAlchemy ORM model for infographic generation.

Uses sqlalchemy.Uuid (dialect-agnostic, available since SQLAlchemy 2.0)
for compatibility with both PostgreSQL (production) and SQLite (tests).
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class InfographicStatus(str, enum.Enum):
    """Lifecycle states for infographic generation."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InfographicGenerationModel(Base):
    """ORM model for infographic_generations table."""

    __tablename__ = "infographic_generations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    post_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(
        String(100), nullable=False, default="cloudflare"
    )
    model: Mapped[str] = mapped_column(
        String(200), nullable=False, default="@cf/black-forest-labs/flux-2-klein-9b"
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=InfographicStatus.PENDING
    )
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=1536)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=864)
    # Hash of the prompt sent to Cloudflare (for deduplication)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Path to the generated PNG file (relative to INFOGRAPHIC_OUTPUT_DIR)
    output_path: Mapped[str] = mapped_column(Text, nullable=True)
    # Error message if generation failed
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationship back to Post
    post: Mapped["PostModel"] = relationship(  # noqa: F821
        "PostModel", foreign_keys=[post_id]
    )
