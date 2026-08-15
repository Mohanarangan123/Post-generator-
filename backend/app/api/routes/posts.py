"""
LinkedIn post API endpoints.

- POST /api/posts/generate/{day_topic_id}  -> generate a post for a day topic
- GET  /api/posts/by-plan/{plan_id}        -> list all posts for a plan
- GET  /api/posts/{post_id}                -> get a specific post
- PUT  /api/posts/{post_id}                -> update post content/status
- POST /api/posts/{post_id}/approve        -> approve a post
- POST /api/posts/{post_id}/regenerate     -> regenerate a post
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.content_plan import DayTopicModel
from app.models.post import PostStatus
from app.schemas.post import BulkGenerationResponse, PostRead, PostResponse, PostUpdate
from app.services.post_repository import PostRepository
from app.services.post_service import generate_post_content

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/posts", tags=["posts"])


@router.post("/generate/{day_topic_id}", response_model=PostResponse)
async def generate_post(
    day_topic_id: UUID, db: Session = Depends(get_db)
) -> PostResponse:
    """Generate a LinkedIn post for a specific day topic."""
    topic = db.query(DayTopicModel).filter(DayTopicModel.id == day_topic_id).first()
    if topic is None:
        raise HTTPException(
            status_code=404, detail=f"DayTopic {day_topic_id} not found."
        )
    repo = PostRepository(db)
    try:
        content = await generate_post_content(topic)
        post = repo.create(
            day_topic_id=day_topic_id, content=content, status=PostStatus.DRAFT
        )
        return PostResponse(success=True, message="Post generated.", post=post)
    except Exception as exc:
        logger.error(
            "Post generation failed for day_topic %s: %s", day_topic_id, exc
        )
        post = repo.create(
            day_topic_id=day_topic_id, content=None, status=PostStatus.FAILED
        )
        return PostResponse(
            success=False, message=f"Generation failed: {exc}", post=post
        )


@router.get("/by-plan/{plan_id}", response_model=list[PostRead])
def list_posts_by_plan(
    plan_id: UUID, db: Session = Depends(get_db)
) -> list[PostRead]:
    """Return all posts for all day topics in a content plan."""
    repo = PostRepository(db)
    posts = repo.list_by_plan(plan_id)
    return [PostRead.model_validate(p) for p in posts]


@router.get("/{post_id}", response_model=PostResponse)
def get_post(post_id: UUID, db: Session = Depends(get_db)) -> PostResponse:
    """Return a specific post by ID."""
    repo = PostRepository(db)
    post = repo.get(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    return PostResponse(success=True, message="Post retrieved.", post=post)


@router.put("/{post_id}", response_model=PostResponse)
def update_post(
    post_id: UUID, body: PostUpdate, db: Session = Depends(get_db)
) -> PostResponse:
    """Update post content and/or status."""
    repo = PostRepository(db)
    post = repo.update(
        post_id=post_id,
        content=body.content,
        status=body.status.value if body.status else None,
    )
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    return PostResponse(success=True, message="Post updated.", post=post)


@router.post("/{post_id}/approve", response_model=PostResponse)
def approve_post(post_id: UUID, db: Session = Depends(get_db)) -> PostResponse:
    """Approve a post (set status to APPROVED)."""
    repo = PostRepository(db)
    post = repo.update(post_id=post_id, status=PostStatus.APPROVED)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    return PostResponse(success=True, message="Post approved.", post=post)


@router.post("/{post_id}/regenerate", response_model=PostResponse)
async def regenerate_post(
    post_id: UUID, db: Session = Depends(get_db)
) -> PostResponse:
    """Regenerate post content using Ollama."""
    repo = PostRepository(db)
    post = repo.get(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    try:
        content = await generate_post_content(post.day_topic)
        updated = repo.update(
            post_id=post_id, content=content, status=PostStatus.DRAFT
        )
        return PostResponse(success=True, message="Post regenerated.", post=updated)
    except Exception as exc:
        logger.error("Regeneration failed for post %s: %s", post_id, exc)
        updated = repo.update(post_id=post_id, status=PostStatus.FAILED)
        return PostResponse(
            success=False, message=f"Regeneration failed: {exc}", post=updated
        )
