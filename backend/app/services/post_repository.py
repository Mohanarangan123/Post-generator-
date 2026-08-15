import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models.content_plan import DayTopicModel
from app.models.post import PostModel, PostStatus

logger = logging.getLogger(__name__)


class PostRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        day_topic_id: UUID,
        content: Optional[str],
        status: str = PostStatus.DRAFT,
    ) -> PostModel:
        post = PostModel(
            id=uuid.uuid4(),
            day_topic_id=day_topic_id,
            content=content,
            status=status,
        )
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)
        return post

    def get(self, post_id: UUID) -> Optional[PostModel]:
        return (
            self.db.query(PostModel)
            .options(joinedload(PostModel.day_topic))
            .filter(PostModel.id == post_id)
            .first()
        )

    def get_by_day_topic(self, day_topic_id: UUID) -> Optional[PostModel]:
        return (
            self.db.query(PostModel)
            .filter(PostModel.day_topic_id == day_topic_id)
            .order_by(PostModel.created_at.desc())
            .first()
        )

    def list_by_plan(self, plan_id: UUID) -> list[PostModel]:
        return (
            self.db.query(PostModel)
            .join(PostModel.day_topic)
            .filter(DayTopicModel.plan_id == plan_id)
            .order_by(DayTopicModel.day_number.asc())
            .all()
        )

    def update(
        self,
        post_id: UUID,
        content: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[PostModel]:
        post = self.db.query(PostModel).filter(PostModel.id == post_id).first()
        if post is None:
            return None
        if content is not None:
            post.content = content
        if status is not None:
            post.status = status
        post.updated_at = datetime.now(timezone.utc)
        post.version += 1
        self.db.commit()
        self.db.refresh(post)
        return post
