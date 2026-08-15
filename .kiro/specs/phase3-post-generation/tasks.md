# Implementation Plan: Phase 3 — LinkedIn Post Generation

## Overview

Implement the post generation pipeline by adding the `PostModel`, `PostStatus` enum, Pydantic schemas, `PostService` (Ollama prompt + retry), `PostRepository` (DB CRUD), FastAPI routes, an Alembic migration, a Streamlit Content Calendar tab, and a full test suite — all without breaking any existing Phase 1/2 code.

## Tasks

- [x] 1. Add PostStatus enum and PostModel ORM
  - Create `backend/app/models/post.py` with `PostStatus(str, enum.Enum)` defining values `DRAFT`, `REVIEW`, `APPROVED`, `SCHEDULED`, `PUBLISHED`, `FAILED`
  - Define `PostModel` in the same file using `sqlalchemy.Uuid(as_uuid=True)` for all UUID columns, matching the `ContentPlanModel` pattern
  - Columns: `id`, `day_topic_id` (FK → `day_topics.id` CASCADE), `content` (Text, nullable), `status` (String(50), default DRAFT), `version` (Integer, default 1), `created_at`, `updated_at`
  - Add `day_topic` relationship to `DayTopicModel` with `back_populates="posts"`
  - Extend `DayTopicModel` in `content_plan.py` with `posts` back-populated relationship (`cascade="all, delete-orphan"`)
  - Import `PostModel` in `backend/app/models/__init__.py` so Alembic autodiscovers it
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Add Alembic migration for posts table
  - Create `backend/alembic/versions/0002_add_posts_table.py` with `down_revision = "0001"`
  - Use `sa.Uuid(as_uuid=True)` (not `postgresql.UUID`) so the migration runs on SQLite in tests
  - `upgrade()`: create `posts` table + index `ix_posts_day_topic_id`
  - `downgrade()`: drop index and table
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 3. Add Pydantic schemas for posts
  - Create `backend/app/schemas/post.py` with `PostCreate`, `PostRead`, `PostUpdate`, `PostResponse`, `BulkGenerationResponse`
  - `PostUpdate.content` validator: strip whitespace, raise `ValueError` if blank (same pattern as `ContentPlanRequest`)
  - `PostRead`: `model_config = {"from_attributes": True}`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 3.1 Write property test for PostUpdate content validation
    - **Property 7: PostUpdate rejects whitespace-only content**
    - **Validates: Requirements 3.3**

- [x] 4. Implement PostService (prompt builder + Ollama caller + retry)
  - Create `backend/app/services/post_service.py`
  - `_build_post_prompt(topic: DayTopicModel) -> str`: embed all seven section markers exactly as specified in the design
  - `_clean_response(raw: str) -> str`: strip `<think>...</think>` and markdown code fences (reuse regex from `curriculum_service.py`)
  - `generate_post_content(topic, retries=3, timeout_seconds=120.0)`: retry loop catching `httpx.ConnectError`, `httpx.TimeoutException`, `httpx.HTTPStatusError`, `ValueError`; raise last exception after exhausting retries
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 4.1 Write property test for prompt structural completeness
    - **Property 1: Prompt contains all required structural markers**
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 4.2 Write property test for prompt field inclusion
    - **Property 2: Prompt contains all DayTopic field values**
    - **Validates: Requirements 4.1**

  - [ ]* 4.3 Write property test for response cleaning idempotence
    - **Property 3: Response cleaning is idempotent**
    - **Validates: Requirements 4.5**

  - [ ]* 4.4 Write property test for think-tag and fence stripping round-trip
    - **Property 4: Think tag and fence stripping recovers original content**
    - **Validates: Requirements 4.5**

- [x] 5. Implement PostRepository (DB CRUD)
  - Create `backend/app/services/post_repository.py`
  - Methods: `create`, `get`, `get_by_day_topic`, `list_by_plan`, `update`
  - `update` must increment `version` by 1 and set `updated_at` to current UTC time
  - Use `joinedload(PostModel.day_topic)` in `get()` to avoid lazy-load issues
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 5.1 Write property test for post creation round-trip
    - **Property 5: Post creation round-trip preserves all fields**
    - **Validates: Requirements 5.1, 5.2, 1.1**

  - [ ]* 5.2 Write property test for update version increment
    - **Property 6: Update increments version by exactly 1**
    - **Validates: Requirements 5.3, 5.6**

- [x] 6. Checkpoint — verify model, migration, schemas, service, and repository
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement PostRouter (post-level CRUD endpoints)
  - Create `backend/app/api/routes/posts.py` with router prefix `/api/posts`
  - Endpoints: `POST /generate/{day_topic_id}`, `GET /{post_id}`, `PUT /{post_id}`, `POST /{post_id}/approve`, `POST /{post_id}/regenerate`, `GET /by-plan/{plan_id}`
  - On generation failure (all retries), create post with `status=FAILED`, return `PostResponse(success=False)` with HTTP 200 (do NOT raise HTTPException)
  - Validate `day_topic_id` exists before generating (return 404 if not found)
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.9_

- [x] 8. Add bulk generation route to ContentPlansRouter
  - Add `POST /{plan_id}/generate-posts` to `backend/app/api/routes/content_plans.py`
  - Accept `max_concurrency: int = 1` query param; use `asyncio.Semaphore(max_concurrency)` for future flexibility
  - Iterate topics sorted by `day_number`; upsert post on each (overwrite existing, reset to DRAFT)
  - Return `BulkGenerationResponse` with generated + failed counts
  - Import `PostRepository`, `PostStatus`, `generate_post_content`, and `BulkGenerationResponse` at the top of the file
  - _Requirements: 6.6, 6.7, 6.8_

  - [ ]* 8.1 Write property test for bulk generation count invariant
    - **Property 9: Bulk generation count invariant**
    - **Validates: Requirements 6.6**

- [x] 9. Register PostRouter in main.py
  - In `backend/app/main.py`: `from app.api.routes.posts import router as posts_router` and `app.include_router(posts_router)`
  - Update the app description string to mention Phase 3
  - _Requirements: 6.9_

- [x] 10. Checkpoint — run the full existing test suite
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Write test suite in backend/tests/test_posts.py
  - Use the same SQLite in-memory fixture pattern as `test_content_plans.py` (copy `db_engine`, `db_session`, `client` fixtures)
  - Add `make_plan_and_topic(db_session)` helper that inserts a `ContentPlanModel` + one `DayTopicModel` directly into the test DB
  - Mock Ollama via `patch("app.services.post_service.httpx.AsyncClient")` using the same `AsyncMock` pattern as Phase 2
  - _Requirements: 8.1_

  - [x] 11.1 Happy-path generation test (status=DRAFT, non-empty content)
    - Call `POST /api/posts/generate/{day_topic_id}` with mocked Ollama
    - Assert `success=True`, `post.status == "DRAFT"`, `post.content` is non-empty
    - _Requirements: 8.2_

  - [x] 11.2 Post persistence round-trip test
    - Generate post → `GET /api/posts/{post_id}` → assert all fields match
    - _Requirements: 8.3_

  - [x] 11.3 Edit post content test
    - Generate post → `PUT /api/posts/{post_id}` with new content → assert `content` updated and `version == 2`
    - _Requirements: 8.4_

  - [x] 11.4 Approval workflow test
    - Generate post → `POST /api/posts/{post_id}/approve` → assert `status == "APPROVED"`
    - _Requirements: 8.5_

  - [x] 11.5 Regeneration test
    - Generate post (version 1) → `POST /api/posts/{post_id}/regenerate` → assert new content and `version == 2`
    - _Requirements: 8.6_

  - [ ] 11.6 Ollama failure → FAILED status test
    - Mock Ollama to raise `httpx.ConnectError` on every attempt → call generate endpoint → assert `success=False`, `post.status == "FAILED"`
    - _Requirements: 8.7_

  - [-] 11.7 Empty Ollama response → FAILED status test
    - Mock Ollama to return `{"response": ""}` → call generate endpoint → assert `post.status == "FAILED"`
    - _Requirements: 8.8_

  - [ ]* 11.8 Write property-based tests using Hypothesis
    - **Property 1: Prompt contains all required structural markers**
    - **Property 2: Prompt contains all DayTopic field values**
    - **Property 3: Response cleaning is idempotent**
    - **Property 4: Think tag and fence stripping recovers original content**
    - **Property 7: PostUpdate rejects whitespace-only content**
    - **Property 8: Post status is always a valid PostStatus value**
    - **Validates: Requirements 4.1, 4.2, 4.5, 3.3, 1.5, 8.9**

- [~] 12. Add Content Calendar tab to Streamlit frontend
  - In `frontend/app.py`: add `put_json` helper (same pattern as `post_json` but using `requests.put`)
  - Change `st.tabs(["📅 Content Planner", "📊 System Status"])` to include `"📋 Content Calendar"` as a third tab
  - Add `render_content_calendar()` function:
    - Plan selector dropdown (populated from `GET /api/content-plans/`)
    - Per-row table: Day | Topic | Status | Actions (Gen / View / Edit / Regen / Approve)
    - "🚀 Generate All Posts" button calling bulk endpoint with 600 s timeout
    - [View] shows `st.expander` with post content, status, timestamp
    - [Edit] shows `st.text_area` pre-filled with current content + [Save] calling `PUT /api/posts/{post_id}`
    - Disable View/Edit/Regen/Approve when no post exists for that row
  - Leave existing `render_content_planner()` and `render_system_status()` completely unchanged
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12_

- [~] 13. Final checkpoint — run the full test suite
  - Ensure all tests in `test_posts.py`, `test_content_plans.py`, and `test_health.py` pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional property/unit tests and can be skipped for a faster MVP; all unmarked tasks are required
- All UUID columns use `sqlalchemy.Uuid(as_uuid=True)` — never `postgresql.UUID` — for SQLite test compatibility
- The `PostService` retry loop uses `retries` and `timeout_seconds` parameters so tests can override them without monkey-patching global config
- The bulk generation endpoint is on the `/api/content-plans` router (not `/api/posts`) to maintain correct REST resource semantics
- Sequential generation (Semaphore(1)) is the default to protect the 16 GB RAM host; the `max_concurrency` param leaves the door open for future parallelism
- Property tests use Hypothesis with the same `@h_settings(max_examples=50)` budget as Phase 2
