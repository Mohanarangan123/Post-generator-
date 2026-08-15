"""
Repository for ContentPlanModel database operations.

Provides create, read, list, and delete operations for content plans.
All DB mutations happen in a single transaction per operation.
"""
import uuid
import logging
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.content_plan import ContentPlanModel, DayTopicModel
from app.schemas.content_plan import ContentPlanRequest, DayTopic

logger = logging.getLogger(__name__)


class ContentPlanRepository:
    """Handles all database operations for ContentPlanModel and DayTopicModel."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def save_plan(
        self,
        request: ContentPlanRequest,
        topics: list[DayTopic],
    ) -> ContentPlanModel:
        """
        Persist a new ContentPlanModel and all associated DayTopicModel records.

        Returns:
            The newly created ContentPlanModel with topics loaded.
        """
        plan = ContentPlanModel(
            id=uuid.uuid4(),
            main_subject=request.main_subject,
            number_of_days=request.number_of_days,
            audience=request.audience,
            difficulty=request.difficulty,
        )
        self.db.add(plan)

        for topic in topics:
            day_topic = DayTopicModel(
                id=uuid.uuid4(),
                plan_id=plan.id,
                day_number=topic.day_number,
                main_subject=topic.main_subject,
                title=topic.title,
                short_description=topic.short_description,
                difficulty=topic.difficulty,
                category=topic.category,
                learning_objective=topic.learning_objective,
            )
            self.db.add(day_topic)

        self.db.commit()
        self.db.refresh(plan)
        logger.info("Saved content plan id=%s ('%s')", plan.id, plan.main_subject)
        return plan

    def list_plans(self) -> list[ContentPlanModel]:
        """Return all ContentPlanModel records ordered by created_at descending."""
        return (
            self.db.query(ContentPlanModel)
            .order_by(ContentPlanModel.created_at.desc())
            .all()
        )

    def get_plan(self, plan_id: UUID) -> ContentPlanModel | None:
        """
        Return a ContentPlanModel with its topics eagerly loaded, or None if not found.
        """
        return (
            self.db.query(ContentPlanModel)
            .options(joinedload(ContentPlanModel.topics))
            .filter(ContentPlanModel.id == plan_id)
            .first()
        )

    def delete_plan(self, plan_id: UUID) -> bool:
        """
        Delete a content plan and all its cascade-deleted day topics.

        Returns:
            True if the plan existed and was deleted; False if not found.
        """
        plan = (
            self.db.query(ContentPlanModel)
            .filter(ContentPlanModel.id == plan_id)
            .first()
        )
        if plan is None:
            return False
        self.db.delete(plan)
        self.db.commit()
        logger.info("Deleted content plan id=%s", plan_id)
        return True
