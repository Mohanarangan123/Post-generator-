"""
SQLAlchemy ORM models for content plans.

Uses sqlalchemy.Uuid (dialect-agnostic, available since SQLAlchemy 2.0)
instead of postgresql.UUID so the models work with both PostgreSQL (production)
and SQLite (tests).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ContentPlanModel(Base):
    """ORM model for the content_plans table."""

    __tablename__ = "content_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    main_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    number_of_days: Mapped[int] = mapped_column(Integer, nullable=False)
    audience: Mapped[str] = mapped_column(String(500), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    topics: Mapped[list["DayTopicModel"]] = relationship(
        "DayTopicModel",
        back_populates="plan",
        cascade="all, delete-orphan",
    )


class DayTopicModel(Base):
    """ORM model for the day_topics table."""

    __tablename__ = "day_topics"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("content_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    main_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(200), nullable=False)
    learning_objective: Mapped[str] = mapped_column(Text, nullable=False)

    plan: Mapped["ContentPlanModel"] = relationship(
        "ContentPlanModel",
        back_populates="topics",
    )

    posts: Mapped[list["PostModel"]] = relationship(  # noqa: F821
        "PostModel",
        back_populates="day_topic",
        cascade="all, delete-orphan",
    )
