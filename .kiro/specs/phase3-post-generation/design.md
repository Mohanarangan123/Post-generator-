# Design Document — Phase 3: LinkedIn Post Generation

## Overview

Phase 3 adds the post generation pipeline on top of the existing Phase 1/2 foundation. The design follows the same patterns established in Phase 2: a SQLAlchemy ORM model, Pydantic schemas, a repository class, a service class that calls Ollama, a FastAPI router, and a Streamlit tab. No existing files are modified except those that explicitly need extension (models, main.py, frontend app.py).

---

## Architecture

```
Streamlit Frontend (app.py)
        │
        │  HTTP (requests)
        ▼
FastAPI Backend
 ├── POST /api/posts/generate/{day_topic_id}
 ├── GET  /api/posts/{post_id}
 ├── PUT  /api/posts/{post_id}
 ├── POST /api/posts/{post_id}/approve
 ├── POST /api/posts/{post_id}/regenerate
 └── POST /api/content-plans/{plan_id}/generate-posts
        │
        ├── PostService  ──────────────► Ollama (httpx, async)
        │
        └── PostRepository ────────────► PostgreSQL (SQLAlchemy)
                                         (SQLite in tests)
```

### Key design decisions

1. **Sequential bulk generation** — `max_concurrency=1` default means `asyncio.Semaphore(1)`, which is effectively sequential. This respects the 16 GB RAM constraint on the host machine running Qwen3 4B.
2. **FAILED-not-500** — When Ollama fails after all retries during single or bulk generation, the post record is written to the database with `status=FAILED`. The API returns `success=False` with HTTP 200 so the frontend can display per-row failure states without treating the whole operation as a server crash.
3. **Dialect-agnostic UUID** — All UUID columns use `sqlalchemy.Uuid(as_uuid=True)` matching the existing models, keeping tests SQLite-compatible.
4. **Retry in service layer** — Retry logic lives in `PostService`, not the router, so it is independently unit-testable.
5. **PostRouter registered on two routers** — Post CRUD routes go on a new `/api/posts` router; the bulk generation route is added to the existing `/api/content-plans` router to keep REST resource semantics correct (`/api/content-plans/{plan_id}/generate-posts`).

---

## New Files

| Path | Purpose |
|---|---|
| `backend/app/models/post.py` | `PostModel` ORM, `PostStatus` enum |
| `backend/app/schemas/post.py` | `PostCreate`, `PostRead`, `PostUpdate`, `PostResponse`, `BulkGenerationResponse` |
| `backend/app/services/post_service.py` | Prompt building, Ollama call, retry logic, response cleaning |
| `backend/app/services/post_repository.py` | DB CRUD for `PostModel` |
| `backend/app/api/routes/posts.py` | FastAPI router for post endpoints |
| `backend/alembic/versions/0002_add_posts_table.py` | Alembic migration |
| `backend/tests/test_posts.py` | Test suite for Phase 3 |

## Modified Files

| Path | Change |
|---|---|
| `backend/app/models/content_plan.py` | Add `posts` relationship to `DayTopicModel` |
| `backend/app/models/__init__.py` | Import `PostModel` so Alembic sees it |
| `backend/app/main.py` | Register `posts_router` and add bulk-generation route to `content_plans_router` |
| `frontend/app.py` | Add "📋 Content Calendar" tab |

---

## Component Details

### PostStatus Enum (`backend/app/models/post.py`)

```python
import enum

class PostStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
```

Using `str` as a mixin means SQLAlchemy can store and retrieve values without a separate `Enum` column type — it maps to a plain `String(50)` column, which is compatible with SQLite and PostgreSQL equally.

### PostModel ORM (`backend/app/models/post.py`)

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base
from app.models.post import PostStatus  # same file

class PostModel(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day_topic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("day_topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default=PostStatus.DRAFT)
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

    day_topic: Mapped["DayTopicModel"] = relationship(
        "DayTopicModel", back_populates="posts"
    )
```

The `DayTopicModel` in `content_plan.py` gets this addition:

```python
posts: Mapped[list["PostModel"]] = relationship(
    "PostModel",
    back_populates="day_topic",
    cascade="all, delete-orphan",
)
```

### Pydantic Schemas (`backend/app/schemas/post.py`)

```python
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
```

### PostService (`backend/app/services/post_service.py`)

```python
import logging
import re
import httpx
from app.core.config import get_settings
from app.models.content_plan import DayTopicModel

logger = logging.getLogger(__name__)

POST_TIMEOUT_SECONDS = 120.0
DEFAULT_RETRIES = 3

def _build_post_prompt(topic: DayTopicModel) -> str:
    return f"""You are a LinkedIn content writer creating educational posts.

Write a LinkedIn post for DAY {topic.day_number}: {topic.title}

Topic details:
- Subject: {topic.main_subject}
- Category: {topic.category}
- Difficulty: {topic.difficulty}
- Description: {topic.short_description}
- Learning objective: {topic.learning_objective}

STRICT FORMAT RULES — follow this structure exactly:
DAY {topic.day_number}: {topic.title}

[A one-sentence hook that grabs attention]

✅ A simple explanation:
[Explain the concept in plain language, 2-3 sentences]

✅ A real-world example:
[One concrete, specific real-world example, 2-3 sentences]

✅ How it works:
[Step-by-step or mechanistic explanation, 3-4 sentences]

✅ Why it matters:
[Business or practical relevance, 2-3 sentences]

💡 Key takeaway:
[One short memorable sentence]

[One engaging question for the reader]

[3 to 5 relevant hashtags, e.g. #Python #MachineLearning]

CONTENT RULES:
- Professional but accessible English — no jargon without explanation
- Short paragraphs for mobile readability
- Use ONLY the ✅ and 💡 symbols shown above — no other emojis
- Do NOT include fake statistics or unsupported claims
- Do NOT add markdown formatting, code fences, or commentary outside the post
- Return ONLY the post text, nothing else"""


def _clean_response(raw: str) -> str:
    """Remove <think>...</think> blocks and markdown code fences from Ollama output."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```(?:\w+)?\s*", "", cleaned).replace("```", "").strip()
    return cleaned


async def generate_post_content(
    topic: DayTopicModel,
    retries: int = DEFAULT_RETRIES,
    timeout_seconds: float = POST_TIMEOUT_SECONDS,
) -> str:
    """
    Generate LinkedIn post content for a DayTopic using Ollama.

    Returns:
        Cleaned post text string.

    Raises:
        Exception: After all retries are exhausted.
        ValueError: If the cleaned response is empty.
    """
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    prompt = _build_post_prompt(topic)
    last_exc: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    url,
                    json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
                )
                response.raise_for_status()
            raw = response.json().get("response", "")
            cleaned = _clean_response(raw)
            if not cleaned:
                raise ValueError("Ollama returned an empty post response.")
            logger.info("Generated post for day %d on attempt %d", topic.day_number, attempt)
            return cleaned
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError) as exc:
            last_exc = exc
            logger.warning(
                "Post generation attempt %d/%d failed for day %d: %s",
                attempt, retries, topic.day_number, exc,
            )

    raise last_exc  # exhausted all retries
```

### PostRepository (`backend/app/services/post_repository.py`)

```python
import uuid
import logging
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.orm import Session, joinedload
from app.models.post import PostModel, PostStatus
from app.models.content_plan import DayTopicModel, ContentPlanModel

logger = logging.getLogger(__name__)

class PostRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, day_topic_id: UUID, content: str | None, status: str = PostStatus.DRAFT) -> PostModel:
        post = PostModel(id=uuid.uuid4(), day_topic_id=day_topic_id, content=content, status=status)
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)
        return post

    def get(self, post_id: UUID) -> PostModel | None:
        return (
            self.db.query(PostModel)
            .options(joinedload(PostModel.day_topic))
            .filter(PostModel.id == post_id)
            .first()
        )

    def get_by_day_topic(self, day_topic_id: UUID) -> PostModel | None:
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

    def update(self, post_id: UUID, content: str | None = None, status: str | None = None) -> PostModel | None:
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
```

### API Router (`backend/app/api/routes/posts.py`)

```python
import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.post import PostResponse, PostUpdate, BulkGenerationResponse
from app.services.post_repository import PostRepository
from app.services.post_service import generate_post_content
from app.models.post import PostStatus
from app.services.content_plan_repository import ContentPlanRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/posts", tags=["posts"])


@router.post("/generate/{day_topic_id}", response_model=PostResponse)
async def generate_post(day_topic_id: UUID, db: Session = Depends(get_db)) -> PostResponse:
    repo = PostRepository(db)
    plan_repo = ContentPlanRepository(db)
    # verify DayTopic exists
    from app.models.content_plan import DayTopicModel
    topic = db.query(DayTopicModel).filter(DayTopicModel.id == day_topic_id).first()
    if topic is None:
        raise HTTPException(status_code=404, detail=f"DayTopic {day_topic_id} not found.")
    try:
        content = await generate_post_content(topic)
        post = repo.create(day_topic_id=day_topic_id, content=content, status=PostStatus.DRAFT)
        return PostResponse(success=True, message="Post generated.", post=post)
    except Exception as exc:
        logger.error("Post generation failed for day_topic %s: %s", day_topic_id, exc)
        post = repo.create(day_topic_id=day_topic_id, content=None, status=PostStatus.FAILED)
        return PostResponse(success=False, message=f"Generation failed: {exc}", post=post)


@router.get("/{post_id}", response_model=PostResponse)
def get_post(post_id: UUID, db: Session = Depends(get_db)) -> PostResponse:
    repo = PostRepository(db)
    post = repo.get(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    return PostResponse(success=True, message="Post retrieved.", post=post)


@router.put("/{post_id}", response_model=PostResponse)
def update_post(post_id: UUID, body: PostUpdate, db: Session = Depends(get_db)) -> PostResponse:
    repo = PostRepository(db)
    post = repo.update(post_id=post_id, content=body.content, status=body.status)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    return PostResponse(success=True, message="Post updated.", post=post)


@router.post("/{post_id}/approve", response_model=PostResponse)
def approve_post(post_id: UUID, db: Session = Depends(get_db)) -> PostResponse:
    repo = PostRepository(db)
    post = repo.update(post_id=post_id, status=PostStatus.APPROVED)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    return PostResponse(success=True, message="Post approved.", post=post)


@router.post("/{post_id}/regenerate", response_model=PostResponse)
async def regenerate_post(post_id: UUID, db: Session = Depends(get_db)) -> PostResponse:
    repo = PostRepository(db)
    post = repo.get(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    try:
        content = await generate_post_content(post.day_topic)
        updated = repo.update(post_id=post_id, content=content, status=PostStatus.DRAFT)
        return PostResponse(success=True, message="Post regenerated.", post=updated)
    except Exception as exc:
        logger.error("Regeneration failed for post %s: %s", post_id, exc)
        updated = repo.update(post_id=post_id, status=PostStatus.FAILED)
        return PostResponse(success=False, message=f"Regeneration failed: {exc}", post=updated)
```

The bulk generation route is added to the existing `content_plans` router:

```python
# In backend/app/api/routes/content_plans.py (new route added at bottom)

@router.post("/{plan_id}/generate-posts", response_model=BulkGenerationResponse)
async def generate_all_posts(
    plan_id: UUID,
    max_concurrency: int = 1,
    db: Session = Depends(get_db),
) -> BulkGenerationResponse:
    plan_repo = ContentPlanRepository(db)
    plan = plan_repo.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Plan {plan_id} not found.")

    post_repo = PostRepository(db)
    results = []
    generated = 0
    failed = 0

    # Sequential (max_concurrency=1 default) — uses asyncio.Semaphore for future flexibility
    import asyncio
    sem = asyncio.Semaphore(max_concurrency)

    async def _generate_one(topic):
        nonlocal generated, failed
        async with sem:
            # Overwrite existing post if present
            existing = post_repo.get_by_day_topic(topic.id)
            try:
                content = await generate_post_content(topic)
                if existing:
                    post = post_repo.update(existing.id, content=content, status=PostStatus.DRAFT)
                else:
                    post = post_repo.create(topic.id, content=content, status=PostStatus.DRAFT)
                generated += 1
                results.append(post)
            except Exception as exc:
                logger.error("Bulk generation failed for topic %s: %s", topic.id, exc)
                if existing:
                    post = post_repo.update(existing.id, status=PostStatus.FAILED)
                else:
                    post = post_repo.create(topic.id, content=None, status=PostStatus.FAILED)
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
```

### Alembic Migration (`backend/alembic/versions/0002_add_posts_table.py`)

```python
"""Add posts table

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "posts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("day_topic_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="DRAFT"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["day_topic_id"], ["day_topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_posts_day_topic_id", "posts", ["day_topic_id"])


def downgrade() -> None:
    op.drop_index("ix_posts_day_topic_id", table_name="posts")
    op.drop_table("posts")
```

### Streamlit Content Calendar Tab (`frontend/app.py` additions)

The new tab is added as a third entry alongside the existing two:

```python
tab1, tab2, tab3 = st.tabs(["📅 Content Planner", "📊 System Status", "📋 Content Calendar"])

with tab3:
    render_content_calendar()
```

```python
def render_content_calendar() -> None:
    st.header("📋 Content Calendar")
    st.caption("Generate, review, edit, and approve LinkedIn posts for each day of a content plan.")

    # Plan selector
    ok, plans_data, err = fetch_json(f"{BACKEND_URL}/api/content-plans/")
    if not ok or plans_data is None:
        st.error(f"Could not load plans: {err}")
        return

    if not plans_data:
        st.info("No content plans found. Go to the Content Planner tab to create one.")
        return

    plan_options = {f"{p['main_subject']} ({p['number_of_days']} days)": p["id"] for p in plans_data}
    selected_label = st.selectbox("Select a content plan", list(plan_options.keys()))
    plan_id = plan_options[selected_label]

    # Load full plan
    ok, plan_resp, err = fetch_json(f"{BACKEND_URL}/api/content-plans/{plan_id}")
    if not ok or plan_resp is None:
        st.error(f"Could not load plan: {err}")
        return

    topics = sorted(plan_resp["plan"]["topics"], key=lambda t: t["day_number"])

    # Load existing posts (list_by_plan)
    ok, posts_resp, _ = fetch_json(f"{BACKEND_URL}/api/posts/by-plan/{plan_id}")
    posts_by_topic: dict[str, dict] = {}
    if ok and posts_resp:
        for post in posts_resp:
            posts_by_topic[post["day_topic_id"]] = post

    # Generate All button
    if st.button("🚀 Generate All Posts"):
        with st.spinner("Generating all posts sequentially — this may take several minutes…"):
            ok, result, err = post_json(
                f"{BACKEND_URL}/api/content-plans/{plan_id}/generate-posts",
                {},
                timeout=600,
            )
        if ok and result:
            st.success(result.get("message", "Done."))
            st.rerun()
        else:
            st.error(f"Bulk generation failed: {err}")

    st.divider()

    # Per-row table
    for topic in topics:
        topic_id = topic["id"]
        post = posts_by_topic.get(topic_id)
        status_label = post["status"] if post else "—"

        col_day, col_topic, col_status, col_actions = st.columns([1, 4, 2, 5])
        with col_day:
            st.write(f"**{topic['day_number']}**")
        with col_topic:
            st.write(topic["title"])
        with col_status:
            st.write(status_label)
        with col_actions:
            a1, a2, a3, a4, a5 = st.columns(5)
            with a1:
                if st.button("Gen", key=f"gen_{topic_id}"):
                    with st.spinner(f"Generating day {topic['day_number']}…"):
                        ok, _, err = post_json(
                            f"{BACKEND_URL}/api/posts/generate/{topic_id}", {}, timeout=180
                        )
                    if ok:
                        st.rerun()
                    else:
                        st.error(err)
            has_post = post is not None
            with a2:
                view_clicked = st.button("View", key=f"view_{topic_id}", disabled=not has_post)
            with a3:
                edit_clicked = st.button("Edit", key=f"edit_{topic_id}", disabled=not has_post)
            with a4:
                if st.button("Regen", key=f"regen_{topic_id}", disabled=not has_post):
                    with st.spinner(f"Regenerating day {topic['day_number']}…"):
                        ok, _, err = post_json(
                            f"{BACKEND_URL}/api/posts/{post['id']}/regenerate", {}, timeout=180
                        )
                    if ok:
                        st.rerun()
                    else:
                        st.error(err)
            with a5:
                if st.button("Approve", key=f"appr_{topic_id}", disabled=not has_post):
                    ok, _, err = post_json(
                        f"{BACKEND_URL}/api/posts/{post['id']}/approve", {}, timeout=10
                    )
                    if ok:
                        st.rerun()
                    else:
                        st.error(err)

        # View expander
        if has_post and view_clicked:
            with st.expander(f"📄 Day {topic['day_number']}: {topic['title']}", expanded=True):
                st.caption(f"Status: {post['status']} | Version: {post['version']} | Generated: {post['created_at']}")
                st.text(post.get("content", ""))

        # Edit area
        if has_post and edit_clicked:
            new_content = st.text_area(
                f"Edit Day {topic['day_number']} post",
                value=post.get("content", ""),
                height=400,
                key=f"textarea_{topic_id}",
            )
            if st.button("💾 Save", key=f"save_{topic_id}"):
                ok, _, err = post_request_put(
                    f"{BACKEND_URL}/api/posts/{post['id']}",
                    {"content": new_content},
                )
                if ok:
                    st.success("Saved.")
                    st.rerun()
                else:
                    st.error(f"Save failed: {err}")
```

The frontend also needs a `put_json` helper (following the same pattern as `post_json`):

```python
def put_json(url: str, payload: dict, timeout: int = REQUEST_TIMEOUT_SECONDS) -> tuple[bool, dict | None, str | None]:
    """PUT JSON to a URL. Returns (success, json_data, error_message). Never raises."""
    try:
        response = requests.put(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return True, response.json(), None
    except requests.exceptions.HTTPError as exc:
        try:
            detail = exc.response.json().get("detail", str(exc))
        except Exception:
            detail = str(exc)
        return False, None, f"API error ({exc.response.status_code}): {detail}"
    except Exception as exc:
        return False, None, f"Unexpected error: {exc}"
```

A `GET /api/posts/by-plan/{plan_id}` convenience endpoint is also needed on the posts router:

```python
@router.get("/by-plan/{plan_id}", response_model=list[PostRead])
def list_posts_by_plan(plan_id: UUID, db: Session = Depends(get_db)) -> list[PostRead]:
    repo = PostRepository(db)
    posts = repo.list_by_plan(plan_id)
    return [PostRead.model_validate(p) for p in posts]
```

---

## Data Flow

### Single Post Generation

```
POST /api/posts/generate/{day_topic_id}
  → verify DayTopicModel exists (404 if not)
  → PostService.generate_post_content(topic, retries=3)
      → build prompt from topic fields
      → call Ollama /api/generate (with retry loop)
      → clean <think> tags and markdown fences
      → return cleaned text
  → PostRepository.create(day_topic_id, content, status=DRAFT)
  → return PostResponse(success=True, post=...)

  [On failure after retries]
  → PostRepository.create(day_topic_id, None, status=FAILED)
  → return PostResponse(success=False, post=...)
```

### Bulk Post Generation

```
POST /api/content-plans/{plan_id}/generate-posts?max_concurrency=1
  → get_plan(plan_id)  (404 if not found)
  → sort topics by day_number
  → for each topic (sequential, Semaphore(1)):
      → check existing post
      → generate or mark FAILED
      → upsert post record
  → return BulkGenerationResponse(generated=N, failed=M, ...)
```

---

## Error Handling

| Scenario | HTTP Status | Response |
|---|---|---|
| DayTopic not found | 404 | `{"detail": "DayTopic {id} not found."}` |
| Post not found | 404 | `{"detail": "Post {id} not found."}` |
| Plan not found (bulk) | 404 | `{"detail": "Plan {id} not found."}` |
| Blank content on update | 422 | Pydantic validation error |
| Ollama fails after retries (single) | 200 | `PostResponse(success=False, post.status=FAILED)` |
| Ollama fails after retries (bulk) | 200 | Counted in `failed`, `BulkGenerationResponse.success=False` |
| Unexpected server error | 500 | Standard FastAPI error |

---

## Testing Strategy

Tests in `backend/tests/test_posts.py` mirror the `test_content_plans.py` patterns:

- **Same SQLite in-memory fixture** — `db_engine`, `db_session`, `client` fixtures with shared connection.
- **Mock Ollama calls** — patch `app.services.post_service.httpx.AsyncClient` (same pattern as Phase 2).
- **Helper factories** — `make_day_topic(db, plan)` creates a real `DayTopicModel` in the test DB.
- **Property-based tests** — Hypothesis validates prompt completeness and input validation properties.

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Prompt contains all required structural markers

For any valid `DayTopic` fields (day_number, title, main_subject, category, difficulty, short_description, learning_objective), the prompt produced by `_build_post_prompt` SHALL contain all seven structural section markers: the DAY header, "✅ A simple explanation", "✅ A real-world example", "✅ How it works", "✅ Why it matters", "💡 Key takeaway", and the hashtag instruction.

**Validates: Requirements 4.1, 4.2**

### Property 2: Prompt contains all DayTopic field values

For any valid `DayTopic` input, every field value (title, day_number as a string, short_description, learning_objective, category, difficulty) SHALL appear verbatim in the generated prompt string.

**Validates: Requirements 4.1**

### Property 3: Response cleaning is idempotent

For any post content string (including strings that contain no think tags and no markdown fences), applying `_clean_response` twice SHALL produce the same result as applying it once.

**Validates: Requirements 4.5**

### Property 4: Think tag and fence stripping recovers original content

For any post content string that does not itself contain `<think>` tags or backtick fences, wrapping it in `<think>preamble</think>` or markdown fences and then passing through `_clean_response` SHALL recover the original content.

**Validates: Requirements 4.5**

### Property 5: Post creation round-trip preserves all fields

For any valid `day_topic_id` (UUID) and non-empty `content` string, creating a post via `PostRepository.create` and then retrieving it via `PostRepository.get` SHALL return a `PostModel` with matching `day_topic_id`, `content`, `status=DRAFT`, and `version=1`.

**Validates: Requirements 5.1, 5.2, 1.1**

### Property 6: Update increments version by exactly 1

For any existing post, calling `PostRepository.update` with a new content value SHALL result in `post.version` being exactly `old_version + 1`, regardless of how many other fields are updated simultaneously.

**Validates: Requirements 5.3, 5.6**

### Property 7: PostUpdate rejects whitespace-only content

For any string composed entirely of whitespace characters (spaces, tabs, newlines), constructing a `PostUpdate` with that string as `content` SHALL raise a Pydantic `ValidationError`.

**Validates: Requirements 3.3**

### Property 8: Post status is always a valid PostStatus value

For any post retrieved from the database (regardless of how it was created or updated), `post.status` SHALL be one of the six valid `PostStatus` enum values: `DRAFT`, `REVIEW`, `APPROVED`, `SCHEDULED`, `PUBLISHED`, or `FAILED`.

**Validates: Requirements 1.5**

### Property 9: Bulk generation count invariant

For any content plan with N day topics, calling `POST /api/content-plans/{plan_id}/generate-posts` SHALL return a `BulkGenerationResponse` where `generated + failed == N`.

**Validates: Requirements 6.6**
