"""
Pydantic schemas for content plan endpoints.
"""
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DayTopic(BaseModel):
    """A single day's topic within a content plan."""
    id: Optional[UUID] = None
    day_number: int
    main_subject: str
    title: str
    short_description: str
    difficulty: str
    category: str
    learning_objective: str


class ContentPlanRequest(BaseModel):
    """Request schema for generating a new content plan."""
    main_subject: str = Field(..., min_length=1)
    audience: str = Field(..., min_length=1)
    difficulty: str = Field(..., min_length=1)
    number_of_days: int = Field(..., ge=1, le=100)

    @field_validator("main_subject", "audience", "difficulty", mode="before")
    @classmethod
    def strip_and_check_not_blank(cls, v: str) -> str:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                raise ValueError("Field must not be blank or whitespace-only.")
            return stripped
        return v


class ContentPlan(BaseModel):
    """Full content plan including all day topics."""
    id: Optional[UUID] = None
    main_subject: str
    number_of_days: int
    audience: str
    difficulty: str
    topics: list[DayTopic]
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ContentPlanResponse(BaseModel):
    """Response schema for content plan endpoints."""
    success: bool
    message: str
    plan: Optional[ContentPlan] = None


class PlanSummary(BaseModel):
    """Summary of a content plan for list views."""
    id: UUID
    main_subject: str
    number_of_days: int
    created_at: datetime

    model_config = {"from_attributes": True}
