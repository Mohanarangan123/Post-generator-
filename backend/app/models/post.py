"""
SQLAlchemy ORM model for posts.

Uses sqlalchemy.Uuid (dialect-agnostic, available since SQLAlchemy 2.0)
instead of postgresql.UUID so the model works with both PostgreSQL (production)
and SQLite (tests).
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PostStatus(str, enum.Enum):
    """Lifecycle states for a generated LinkedIn post."""

    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class PostModel(Base):
    """ORM model for the posts table."""

    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    day_topic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("day_topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    # content is nullable — use plain str annotation; nullable=True on the column governs DB nullability.
    # Mapped[Optional[str]] triggers a Python 3.14 + SQLAlchemy compat issue, so we avoid it.
    content: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=PostStatus.DRAFT
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    day_topic: Mapped["DayTopicModel"] = relationship(  # noqa: F821
        "DayTopicModel", back_populates="posts"
    )

    images: Mapped[list["ImageModel"]] = relationship(  # noqa: F821
        "ImageModel",
        back_populates="post",
        cascade="all, delete-orphan",
    )
