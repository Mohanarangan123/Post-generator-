from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.post import PostStatus


class PostCreate(BaseModel):
    day_topic_id: UUID


class PostRead(BaseModel):
    id: UUID
    day_topic_id: UUID
    content: Optional[str]
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PostUpdate(BaseModel):
    content: str = Field(..., min_length=1)
    status: Optional[PostStatus] = None

    @field_validator("content", mode="before")
    @classmethod
    def strip_and_check_not_blank(cls, v: str) -> str:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("content must not be blank or whitespace-only.")
            return stripped
        return v


class PostResponse(BaseModel):
    success: bool
    message: str
    post: Optional[PostRead] = None


class BulkGenerationResponse(BaseModel):
    success: bool
    message: str
    generated: int
    failed: int
    results: list[PostRead]
