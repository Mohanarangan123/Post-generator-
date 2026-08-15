"""
Content plan API endpoints.

- POST /api/content-plans/generate  -> generate + persist a new plan
- GET  /api/content-plans/          -> list all plan summaries
- GET  /api/content-plans/{plan_id} -> get a full plan by id
- DELETE /api/content-plans/{plan_id} -> delete a plan
- POST /api/content-plans/{plan_id}/generate-posts -> bulk generate posts for a plan
"""
import asyncio
import logging
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.post import PostStatus
from app.schemas.post import BulkGenerationResponse
from app.services.post_repository import PostRepository
from app.services.post_service import generate_post_content

from app.db.session import get_db
from app.schemas.content_plan import (
    ContentPlan,
    ContentPlanRequest,
    ContentPlanResponse,
    DayTopic,
    PlanSummary,
)
from app.services.content_plan_repository import ContentPlanRepository
from app.services.curriculum_service import generate_curriculum

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/content-plans", tags=["content-plans"])


def _model_to_content_plan(plan_model) -> ContentPlan:
    """Convert a ContentPlanModel ORM object to a ContentPlan Pydantic schema."""
    topics = [
        DayTopic(
            id=t.id,
            day_number=t.day_number,
            main_subject=t.main_subject,
            title=t.title,
            short_description=t.short_description,
            difficulty=t.difficulty,
            category=t.category,
            learning_objective=t.learning_objective,
        )
        for t in sorted(plan_model.topics, key=lambda x: x.day_number)
    ]
    return ContentPlan(
        id=plan_model.id,
        main_subject=plan_model.main_subject,
        number_of_days=plan_model.number_of_days,
        audience=plan_model.audience,
        difficulty=plan_model.difficulty,
        topics=topics,
        created_at=plan_model.created_at,
    )


@router.post("/generate", response_model=ContentPlanResponse)
async def generate_plan(
    request: ContentPlanRequest,
    db: Session = Depends(get_db),
) -> ContentPlanResponse:
    """
    Generate a day-by-day content plan using the local LLM and persist it.

    Error mapping:
    - httpx.ConnectError -> 503 Service Unavailable
    - httpx.TimeoutException -> 504 Gateway Timeout
    - httpx.HTTPStatusError -> 502 Bad Gateway
    - ValueError (parse/validation) -> 422 Unprocessable Entity
    - Exception (unexpected) -> 500 Internal Server Error
    """
    try:
        topics = await generate_curriculum(
            main_subject=request.main_subject,
            number_of_days=request.number_of_days,
            audience=request.audience,
            difficulty=request.difficulty,
        )
        repo = ContentPlanRepository(db)
        plan_model = repo.save_plan(request, topics)
        plan = _model_to_content_plan(plan_model)
        return ContentPlanResponse(
            success=True,
            message=f"Generated {len(topics)}-day plan for '{request.main_subject}'.",
            plan=plan,
        )
    except httpx.ConnectError as exc:
        logger.error("Ollama unreachable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Ollama server is unreachable. Ensure Ollama is running.",
        )
    except httpx.TimeoutException as exc:
        logger.error("Ollama request timed out: %s", exc)
        raise HTTPException(
            status_code=504,
            detail="Request to Ollama timed out. Try again or reduce number_of_days.",
        )
    except httpx.HTTPStatusError as exc:
        logger.error("Ollama returned error status: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Ollama returned an error: {exc.response.status_code}",
        )
    except ValueError as exc:
        logger.error("Curriculum validation error: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Unexpected error generating plan: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.get("/", response_model=list[PlanSummary])
def list_plans(db: Session = Depends(get_db)) -> list[PlanSummary]:
    """Return a summary list of all stored content plans."""
    repo = ContentPlanRepository(db)
    plans = repo.list_plans()
    return [PlanSummary.model_validate(p) for p in plans]


@router.get("/{plan_id}", response_model=ContentPlanResponse)
def get_plan(plan_id: UUID, db: Session = Depends(get_db)) -> ContentPlanResponse:
    """Return a full content plan with all day topics."""
    repo = ContentPlanRepository(db)
    plan_model = repo.get_plan(plan_id)
    if plan_model is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found.")
    plan = _model_to_content_plan(plan_model)
    return ContentPlanResponse(success=True, message="Plan retrieved.", plan=plan)


@router.delete("/{plan_id}")
def delete_plan(plan_id: UUID, db: Session = Depends(get_db)) -> dict:
    """Delete a content plan and all its day topics."""
    repo = ContentPlanRepository(db)
    deleted = repo.delete_plan(plan_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found.")
    return {"message": f"Plan {plan_id} deleted successfully."}


@router.post("/{plan_id}/generate-posts", response_model=BulkGenerationResponse)
async def generate_all_posts(
    plan_id: UUID,
    max_concurrency: int = 1,
    db: Session = Depends(get_db),
) -> BulkGenerationResponse:
    """Generate LinkedIn posts for all day topics in a plan sequentially."""
    repo = ContentPlanRepository(db)
    plan = repo.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found.")

    post_repo = PostRepository(db)
    results = []
    generated = 0
    failed = 0

    sem = asyncio.Semaphore(max_concurrency)

    async def _generate_one(topic) -> None:
        nonlocal generated, failed
        async with sem:
            existing = post_repo.get_by_day_topic(topic.id)
            try:
                content = await generate_post_content(topic)
                if existing:
                    post = post_repo.update(
                        existing.id, content=content, status=PostStatus.DRAFT
                    )
                else:
                    post = post_repo.create(
                        topic.id, content=content, status=PostStatus.DRAFT
                    )
                generated += 1
                results.append(post)
            except Exception as exc:
                logger.error(
                    "Bulk generation failed for topic %s: %s", topic.id, exc
                )
                if existing:
                    post = post_repo.update(existing.id, status=PostStatus.FAILED)
                else:
                    post = post_repo.create(
                        topic.id, content=None, status=PostStatus.FAILED
                    )
                failed += 1
                results.append(post)

    topics_sorted = sorted(plan.topics, key=lambda t: t.day_number)
    for topic in topics_sorted:
        await _generate_one(topic)

    return BulkGenerationResponse(
        success=failed == 0,
        message=f"Generated {generated} posts, {failed} failed.",
        generated=generated,
        failed=failed,
        results=results,
    )
