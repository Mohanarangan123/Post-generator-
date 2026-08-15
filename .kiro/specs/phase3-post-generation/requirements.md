# Requirements Document

## Introduction

Phase 3 extends the LinkedIn AI Content Generator with post generation capabilities. For every `DayTopic` in a content plan, the system generates a structured, educational LinkedIn post using the local Ollama LLM (Qwen3 4B). Posts follow a fixed seven-section format (hook, simple explanation, real-world example, how it works, why it matters, key takeaway, question + hashtags). Posts are persisted in PostgreSQL with a lifecycle status enum. A new "📋 Content Calendar" tab in the Streamlit frontend exposes per-row generation, viewing, editing, regeneration, and approval actions. All Phase 1 and Phase 2 functionality must remain unaffected.

## Glossary

- **Post**: A generated LinkedIn educational post associated with exactly one `DayTopic`.
- **PostModel**: The SQLAlchemy ORM model representing the `posts` table.
- **PostStatus**: Enum of post lifecycle states: `DRAFT`, `REVIEW`, `APPROVED`, `SCHEDULED`, `PUBLISHED`, `FAILED`.
- **PostService**: The Python service class that constructs prompts, calls Ollama, parses responses, and applies retry logic.
- **PostRepository**: The Python repository class that wraps all database operations for `PostModel`.
- **PostRouter**: The FastAPI `APIRouter` that exposes all post-related REST endpoints.
- **BulkGenerationJob**: The server-side coroutine that generates posts for all `DayTopic` records of a plan sequentially.
- **DayTopic**: An existing Phase 2 ORM model (`DayTopicModel`) representing one day's topic within a content plan.
- **ContentPlan**: An existing Phase 2 ORM model (`ContentPlanModel`) representing a multi-day learning plan.
- **ContentCalendarTab**: The new Streamlit tab ("📋 Content Calendar") added to the frontend.
- **Ollama**: The local LLM server used for content generation.

---

## Requirements

### Requirement 1 — Post Data Model

**User Story:** As a developer, I want a `Post` database model with full lifecycle tracking, so that generated posts can be stored, updated, and tracked through their publishing journey.

#### Acceptance Criteria

1. THE `PostModel` SHALL define columns `id` (UUID primary key, default `uuid4`), `day_topic_id` (UUID foreign key to `day_topics.id` with `ondelete="CASCADE"`), `content` (Text, nullable), `status` (String(50), default `"DRAFT"`, not nullable), `version` (Integer, default `1`, not nullable), `created_at` (DateTime with timezone, auto-set to UTC now), and `updated_at` (DateTime with timezone, auto-set and auto-updated to UTC now).
2. THE `PostModel` SHALL use `sqlalchemy.Uuid(as_uuid=True)` (dialect-agnostic) for all UUID columns, consistent with the existing `ContentPlanModel` and `DayTopicModel`.
3. THE `PostModel` SHALL define a SQLAlchemy `relationship` back to `DayTopicModel` so that `post.day_topic` is accessible without additional queries.
4. THE `DayTopicModel` SHALL be extended with a `posts` back-populated relationship to `PostModel` with `cascade="all, delete-orphan"`.
5. THE `PostStatus` SHALL be a Python `enum.Enum` (or `str` enum) with values `DRAFT`, `REVIEW`, `APPROVED`, `SCHEDULED`, `PUBLISHED`, and `FAILED`.

### Requirement 2 — Alembic Migration

**User Story:** As a developer, I want a new Alembic migration that adds the `posts` table, so that the database schema is version-controlled and reproducible.

#### Acceptance Criteria

1. THE migration file `0002_add_posts_table.py` SHALL create a `posts` table with columns matching Requirement 1.1, using `sa.Uuid` (dialect-agnostic, not `postgresql.UUID`) so the migration runs on both PostgreSQL and SQLite.
2. THE migration `0002_add_posts_table.py` SHALL set `down_revision = "0001"` to chain correctly after the existing migration.
3. THE migration `downgrade()` function SHALL drop the `posts` table and its index, restoring the database to the `0001` state.
4. THE migration SHALL create an index `ix_posts_day_topic_id` on the `day_topic_id` column.

### Requirement 3 — Pydantic Schemas

**User Story:** As a developer, I want Pydantic schemas for posts, so that API request and response data is validated and serialized consistently.

#### Acceptance Criteria

1. THE `PostCreate` schema SHALL contain `day_topic_id` (UUID) as its only required field.
2. THE `PostRead` schema SHALL contain all fields from Requirement 1.1 and SHALL be configured with `model_config = {"from_attributes": True}` to support ORM-mode serialisation.
3. THE `PostUpdate` schema SHALL contain a `content` field (non-empty string, stripped of leading/trailing whitespace) and an optional `status` field restricted to valid `PostStatus` values.
4. THE `PostResponse` schema SHALL contain `success` (bool), `message` (str), and an optional `post` field of type `PostRead`.
5. THE `BulkGenerationResponse` schema SHALL contain `success` (bool), `message` (str), `generated` (int count of successfully generated posts), `failed` (int count of failed posts), and `results` (list of `PostRead`).

### Requirement 4 — Post Generation Service

**User Story:** As a developer, I want a `PostService` that builds prompts, calls Ollama, parses the response, and retries on failure, so that post content is reliably generated from `DayTopic` data.

#### Acceptance Criteria

1. THE `PostService` SHALL construct a prompt using the `DayTopic` fields (`day_number`, `title`, `short_description`, `learning_objective`, `category`, `difficulty`) that instructs Ollama to produce a post matching the seven-section structure: DAY XX header, hook, simple explanation (✅), real-world example (✅), how it works (✅), why it matters (✅), key takeaway (💡), one engaging question, and 3–5 relevant hashtags.
2. THE prompt SHALL explicitly instruct Ollama to use professional but accessible English, avoid excessive emojis (only the ✅ and 💡 symbols in the specified sections), avoid fake statistics, avoid unsupported claims, use short paragraphs for mobile readability, and return only the post text with no extra commentary or markdown fences.
3. WHEN an Ollama call fails with `httpx.ConnectError`, `httpx.TimeoutException`, or `httpx.HTTPStatusError`, THE `PostService` SHALL retry the call up to a configurable number of times (default 3) with no mandatory delay between retries.
4. WHEN all retries are exhausted without a successful response, THE `PostService` SHALL raise an exception that the caller can catch to store the post with `status = FAILED`.
5. THE `PostService` SHALL strip `<think>...</think>` blocks and markdown code fences from Ollama's raw response before returning the cleaned post text, reusing the regex cleaning logic already present in `curriculum_service.py`.
6. WHEN the cleaned Ollama response is an empty string, THE `PostService` SHALL raise a `ValueError` so the caller treats the generation as failed.
7. THE `PostService` SHALL accept configurable `retries` and `timeout_seconds` parameters so they can be overridden in tests without monkey-patching.

### Requirement 5 — Post Repository

**User Story:** As a developer, I want a `PostRepository` that encapsulates all database operations for posts, so that the API layer stays thin and testable.

#### Acceptance Criteria

1. THE `PostRepository` SHALL provide a `create(day_topic_id, content, status)` method that inserts a new `PostModel` and returns it.
2. THE `PostRepository` SHALL provide a `get(post_id)` method that returns the `PostModel` or `None` if not found, with `day_topic` eagerly loaded.
3. THE `PostRepository` SHALL provide an `update(post_id, content, status)` method that applies partial updates and commits, returning the updated `PostModel` or `None` if not found.
4. THE `PostRepository` SHALL provide a `get_by_day_topic(day_topic_id)` method that returns the most recent `PostModel` for the given `DayTopic`, or `None` if none exists.
5. THE `PostRepository` SHALL provide a `list_by_plan(plan_id)` method that returns all `PostModel` records for all `DayTopic` records belonging to the given `ContentPlan`, ordered by `day_number` ascending.
6. WHEN `update` is called, THE `PostRepository` SHALL set `updated_at` to the current UTC time and increment `version` by 1.

### Requirement 6 — API Endpoints

**User Story:** As a frontend developer, I want REST API endpoints for generating, reading, editing, approving, and regenerating posts, so that the Streamlit UI can interact with post data.

#### Acceptance Criteria

1. `POST /api/posts/generate/{day_topic_id}` SHALL call `PostService` to generate post content, persist the post via `PostRepository`, and return a `PostResponse` with the created post; if generation fails after all retries, it SHALL persist the post with `status = FAILED` and return a `PostResponse` with `success = False` and status code `200` (not a server error).
2. `GET /api/posts/{post_id}` SHALL return a `PostResponse` with the requested post, or a `404` if the post does not exist.
3. `PUT /api/posts/{post_id}` SHALL accept a `PostUpdate` body, apply the update via `PostRepository`, and return the updated `PostResponse`; it SHALL return `404` if the post does not exist and `422` if the content is blank or whitespace-only.
4. `POST /api/posts/{post_id}/approve` SHALL set the post's status to `APPROVED` and return the updated `PostResponse`; it SHALL return `404` if the post does not exist.
5. `POST /api/posts/{post_id}/regenerate` SHALL call `PostService` to produce new content, increment `version`, update the post record, and return the updated `PostResponse`; if generation fails, it SHALL update status to `FAILED` and return `PostResponse` with `success = False`.
6. `POST /api/content-plans/{plan_id}/generate-posts` SHALL accept an optional query parameter `max_concurrency` (integer, default 1) and iterate over all `DayTopic` records of the plan sequentially (one at a time when `max_concurrency = 1`), generating or updating a post for each; it SHALL return a `BulkGenerationResponse` summarising generated and failed counts.
7. WHEN `POST /api/content-plans/{plan_id}/generate-posts` is called for a plan that does not exist, THE `PostRouter` SHALL return `404`.
8. WHEN `POST /api/content-plans/{plan_id}/generate-posts` is called and a `DayTopic` already has an existing post, THE `PostRouter` SHALL overwrite that post's content and reset its status to `DRAFT`.
9. THE `PostRouter` SHALL be registered under the prefix `/api/posts` with tag `"posts"` for the post-level routes, and the bulk generation route SHALL be added to the existing `/api/content-plans` router.

### Requirement 7 — Streamlit Content Calendar Tab

**User Story:** As a content creator, I want a "📋 Content Calendar" tab in the Streamlit app, so that I can generate, view, edit, and approve LinkedIn posts for each day of a plan.

#### Acceptance Criteria

1. THE `ContentCalendarTab` SHALL display a plan selector (dropdown populated from `GET /api/content-plans/`) above the calendar table.
2. THE `ContentCalendarTab` SHALL display a table with columns: Day, Topic, Status, and Actions for each `DayTopic` of the selected plan.
3. WHEN a plan is selected, THE `ContentCalendarTab` SHALL fetch existing posts for that plan and display each post's status alongside its topic row.
4. THE Actions column SHALL render per-row buttons: [Generate], [View], [Edit], [Regenerate], and [Approve] for each `DayTopic` row.
5. WHEN the [Generate] button is clicked, THE `ContentCalendarTab` SHALL call `POST /api/posts/generate/{day_topic_id}`, display a spinner during generation, and refresh the table on completion.
6. WHEN the [View] button is clicked, THE `ContentCalendarTab` SHALL display the post content, status, and generation timestamp in a `st.expander` below the table row.
7. WHEN the [Edit] button is clicked, THE `ContentCalendarTab` SHALL display a `st.text_area` pre-filled with the current post content and a [Save] button; clicking [Save] SHALL call `PUT /api/posts/{post_id}` with the edited content.
8. WHEN the [Regenerate] button is clicked, THE `ContentCalendarTab` SHALL call `POST /api/posts/{post_id}/regenerate` with a spinner and refresh the table on completion.
9. WHEN the [Approve] button is clicked, THE `ContentCalendarTab` SHALL call `POST /api/posts/{post_id}/approve` and refresh the table on completion.
10. THE `ContentCalendarTab` SHALL display a "🚀 Generate All Posts" button that calls `POST /api/content-plans/{plan_id}/generate-posts` with a spinner and refreshes the table on completion.
11. WHERE a `DayTopic` has no post yet, THE `ContentCalendarTab` SHALL show status as `—` and disable [View], [Edit], [Regenerate], and [Approve] buttons.
12. THE existing "📅 Content Planner" and "📊 System Status" tabs SHALL remain fully functional and visually unchanged.

### Requirement 8 — Tests

**User Story:** As a developer, I want a comprehensive test suite in `backend/tests/test_posts.py`, so that all post generation, persistence, and API behaviours are verified automatically.

#### Acceptance Criteria

1. THE test file `test_posts.py` SHALL use the same SQLite in-memory fixture pattern (shared connection, `Base.metadata.create_all`, `app.dependency_overrides`) as `test_content_plans.py`.
2. THE test suite SHALL include a test that verifies a post is created with `status = DRAFT` and non-empty `content` when Ollama returns a valid response.
3. THE test suite SHALL include a test that verifies a post round-trip: generate → read back via `GET /api/posts/{post_id}` → assert fields match.
4. THE test suite SHALL include a test that verifies editing post content via `PUT /api/posts/{post_id}` updates both `content` and `version`.
5. THE test suite SHALL include a test that verifies `POST /api/posts/{post_id}/approve` transitions status to `APPROVED`.
6. THE test suite SHALL include a test that verifies `POST /api/posts/{post_id}/regenerate` produces new content and increments `version`.
7. THE test suite SHALL include a test that verifies when Ollama raises `httpx.ConnectError` after all retries, the post is stored with `status = FAILED` and the API returns `success = False`.
8. THE test suite SHALL include a test that verifies when Ollama returns an empty string response, the post is stored with `status = FAILED`.
9. THE test suite SHALL include property-based tests using Hypothesis that validate generation output invariants across varied topic inputs.
10. ALL existing tests in `test_content_plans.py` and `test_health.py` SHALL continue to pass without modification.
