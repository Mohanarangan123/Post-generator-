# Design Document: Phase 2 — AI-Powered LinkedIn Content Planner

## Overview

Phase 2 extends the existing FastAPI + Streamlit foundation (Phase 1) with a complete AI-powered content planning system. Users supply a subject, duration, audience, and difficulty level; the system prompts a locally-running Qwen3 4B model via Ollama, parses the JSON response into a structured day-by-day learning plan, persists it in PostgreSQL, and serves it through a clean API and Streamlit UI.

Phase 1 health/status endpoints and the Phase 1 dashboard are preserved without modification. The only change to existing Phase 1 files is registering the new router in `app/main.py`.

**Tech stack (additive to Phase 1):**
- `httpx` (already in `requirements.txt`) — async-capable HTTP client for Ollama calls
- `alembic` (already in `requirements.txt`) — database migrations
- `pytest-asyncio` — async test support (new addition to `requirements.txt`)
- `python-ulid` or `uuid` (standard library) — UUID primary key generation
- SQLAlchemy 2.x ORM (already present)

---

## Architecture

```mermaid
flowchart TD
    subgraph Frontend
        ST[Streamlit UI\nfrontend/app.py]
    end

    subgraph Backend [FastAPI Backend]
        RT[POST /api/content-plans/generate\nGET /api/content-plans/\nGET /api/content-plans/{id}\nDELETE /api/content-plans/{id}]
        CS[Curriculum Service\ncurriculum_service.py]
        JP[JSON Parser\n_embedded in curriculum_service_]
        DD[Duplicate Detector\n_embedded in curriculum_service_]
        PR[Plan Repository\ncontent_plan_repository.py]
    end

    subgraph External
        OL[Ollama Server\nqwen3:4b]
        DB[(PostgreSQL\ncontent_plans\nday_topics)]
    end

    ST -- HTTP --> RT
    RT --> CS
    CS --> JP
    CS --> DD
    RT --> PR
    CS -- httpx POST /api/generate --> OL
    PR -- SQLAlchemy --> DB
```

**Request lifecycle for plan generation:**

1. Streamlit UI sends POST to `/api/content-plans/generate`
2. FastAPI validates the `ContentPlanRequest` via Pydantic
3. Route handler calls `Curriculum_Service.generate_curriculum(...)`
4. `Curriculum_Service` builds a structured prompt and POSTs to Ollama (non-streaming)
5. Raw text response is extracted from the Ollama JSON envelope
6. `JSON_Parser` strips noise and parses the JSON array
7. `Duplicate_Detector` validates day number sequence and title uniqueness
8. Route handler calls `Plan_Repository.save_plan(...)` to persist to PostgreSQL
9. Full `ContentPlanResponse` is returned

---

## Components and Interfaces

### 1. Pydantic Schemas — `app/schemas/content_plan.py`

```python
from datetime import datetime
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class DayTopic(BaseModel):
    day_number: int
    main_subject: str
    title: str
    short_description: str
    difficulty: str
    category: str
    learning_objective: str

class ContentPlan(BaseModel):
    id: Optional[UUID] = None
    main_subject: str
    number_of_days: int
    audience: str
    difficulty: str
    topics: list[DayTopic]
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class ContentPlanRequest(BaseModel):
    main_subject: str = Field(..., min_length=1, strip_whitespace=True)
    number_of_days: int = Field(..., ge=1, le=100)
    audience: str = Field(..., min_length=1, strip_whitespace=True)
    difficulty: str = Field(..., min_length=1, strip_whitespace=True)

class ContentPlanResponse(BaseModel):
    success: bool
    message: str
    plan: Optional[ContentPlan] = None
```

**Validator notes:**
- `Field(strip_whitespace=True)` with `min_length=1` handles whitespace-only rejection for string fields.
- `ge=1, le=100` enforces the day range.

---

### 2. SQLAlchemy Models — `app/models/content_plan.py`

```python
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.db.base import Base

class ContentPlanModel(Base):
    __tablename__ = "content_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
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
        "DayTopicModel", back_populates="plan", cascade="all, delete-orphan"
    )

class DayTopicModel(Base):
    __tablename__ = "day_topics"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("content_plans.id", ondelete="CASCADE"), nullable=False
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    main_subject: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(200), nullable=False)
    learning_objective: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped["ContentPlanModel"] = relationship("ContentPlanModel", back_populates="topics")
```

**Key decisions:**
- `UUID` primary keys using `postgresql.UUID(as_uuid=True)` for native PostgreSQL UUID type.
- `cascade="all, delete-orphan"` on the relationship + `ondelete="CASCADE"` on the FK ensures topics are removed when the parent plan is deleted, at both ORM and DB levels.
- `DateTime(timezone=True)` stores timestamps as UTC-aware.

---

### 3. Curriculum Service — `app/services/curriculum_service.py`

This is the core business logic component.

#### 3a. Prompt Construction

The prompt is built as a multi-part instruction block:

```
You are a LinkedIn learning curriculum designer.

Generate a {number_of_days}-day learning plan about "{main_subject}" for "{audience}" at {difficulty} level.

STRICT OUTPUT RULES:
- Return ONLY a valid JSON array. No markdown, no code fences, no commentary, no <think> tags.
- The array must contain exactly {number_of_days} objects.
- Each object must have these exact keys:
  "day_number" (integer, 1 to {number_of_days}),
  "main_subject" (string, the overall subject),
  "title" (string, concise unique topic title, max 10 words),
  "short_description" (string, 1-2 sentences),
  "difficulty" (string, e.g. Beginner/Intermediate/Advanced),
  "category" (string, thematic grouping),
  "learning_objective" (string, real-world measurable outcome starting with an action verb)

CURRICULUM RULES:
- Day 1 must start with fundamentals/prerequisites. Progress logically toward advanced concepts.
- Every topic title must be unique. No duplicate or near-duplicate titles allowed.
- Every day_number must be unique and sequential from 1 to {number_of_days}.
- Topics must be directly relevant to "{main_subject}". No off-topic or loosely related topics.
- Learning objectives must be practical and achievable in one day.

Return the JSON array now:
```

#### 3b. LLM Call via Ollama_Client

```python
async def _call_ollama(prompt: str) -> str:
    """POST to Ollama /api/generate (non-streaming). Returns the response text."""
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    data = response.json()
    return data["response"]
```

**Timeout:** 120 seconds — Qwen3 4B can be slow for long plans. Configurable via settings in future phases.

#### 3c. JSON_Parser — Extract and Repair

```python
def _parse_json_array(raw: str) -> list[dict]:
    """
    Extract the first valid JSON array from raw text.
    Strips markdown fences, <think> blocks, and leading/trailing noise.
    Raises ValueError with a descriptive message if no valid array found.
    """
    # 1. Strip <think>...</think> blocks (Qwen3 thinking mode)
    import re
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # 2. Strip markdown code fences
    raw = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    # 3. Try direct parse first
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 4. Extract first [...] substring
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(raw[start:end + 1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"LLM response could not be parsed as a JSON array. "
        f"Raw response (first 500 chars): {raw[:500]}"
    )
```

#### 3d. Duplicate_Detector — Validation

```python
def _validate_topics(topics: list[DayTopic], expected_count: int) -> None:
    """Validate sequential day numbers and unique titles."""
    # Day number validation
    day_numbers = [t.day_number for t in topics]
    if sorted(day_numbers) != list(range(1, expected_count + 1)):
        raise ValueError(
            f"Day numbers are not sequential 1..{expected_count}. Got: {sorted(day_numbers)}"
        )

    # Title uniqueness (exact)
    titles = [t.title.strip().lower() for t in topics]
    seen = set()
    duplicates = []
    for title in titles:
        if title in seen:
            duplicates.append(title)
        seen.add(title)
    if duplicates:
        raise ValueError(f"Duplicate topic titles detected: {duplicates}")
```

#### 3e. Public Interface

```python
async def generate_curriculum(
    main_subject: str,
    number_of_days: int,
    audience: str,
    difficulty: str,
) -> list[DayTopic]:
    """
    Generate a day-by-day learning curriculum using Ollama.
    Returns a validated list of DayTopic objects.
    Raises:
        httpx.ConnectError: if Ollama is unreachable
        httpx.TimeoutException: if request times out
        ValueError: if response cannot be parsed or fails validation
    """
    prompt = _build_prompt(main_subject, number_of_days, audience, difficulty)
    raw = await _call_ollama(prompt)
    raw_list = _parse_json_array(raw)
    topics = [DayTopic(**item) for item in raw_list]
    _validate_topics(topics, number_of_days)
    return topics
```

---

### 4. Plan Repository — `app/services/content_plan_repository.py`

```python
class ContentPlanRepository:
    def __init__(self, db: Session): ...

    def save_plan(self, request: ContentPlanRequest, topics: list[DayTopic]) -> ContentPlanModel:
        """Persist a new ContentPlanModel and all DayTopicModels."""

    def list_plans(self) -> list[ContentPlanModel]:
        """Return all plans (id, main_subject, number_of_days, created_at)."""

    def get_plan(self, plan_id: UUID) -> ContentPlanModel | None:
        """Return a plan with its topics by ID, or None."""

    def delete_plan(self, plan_id: UUID) -> bool:
        """Delete a plan and cascade-delete its topics. Returns True if found."""
```

---

### 5. API Router — `app/api/routes/content_plans.py`

```python
router = APIRouter(prefix="/api/content-plans", tags=["content-plans"])

@router.post("/generate", response_model=ContentPlanResponse)
async def generate_plan(request: ContentPlanRequest, db: Session = Depends(get_db)):
    ...

@router.get("/", response_model=list[PlanSummary])
def list_plans(db: Session = Depends(get_db)):
    ...

@router.get("/{plan_id}", response_model=ContentPlanResponse)
def get_plan(plan_id: UUID, db: Session = Depends(get_db)):
    ...

@router.delete("/{plan_id}")
def delete_plan(plan_id: UUID, db: Session = Depends(get_db)):
    ...
```

**Error mapping in `generate_plan`:**

| Exception | HTTP Response |
|---|---|
| `httpx.ConnectError` | 503 Service Unavailable |
| `httpx.TimeoutException` | 504 Gateway Timeout |
| `httpx.HTTPStatusError` | 502 Bad Gateway |
| `ValueError` (parse/validation) | 422 Unprocessable Entity |
| `Exception` (unexpected) | 500 Internal Server Error |

The router is registered in `app/main.py` by adding:
```python
from app.api.routes.content_plans import router as content_plans_router
app.include_router(content_plans_router)
```

---

### 6. Alembic Configuration

**File structure:**
```
backend/
  alembic.ini          ← points to migrations in backend/alembic/
  alembic/
    env.py             ← imports Base and all models
    versions/
      0001_initial_content_plan_tables.py
```

**`env.py` critical imports:**
```python
from app.db.base import Base
import app.models.content_plan  # noqa: F401 — ensures models are registered
target_metadata = Base.metadata
```

**`alembic.ini` key setting:**
```
script_location = alembic
sqlalchemy.url = postgresql+psycopg://postgres:postgres@localhost:5432/linkedin_ai
```

The `sqlalchemy.url` is overridden in `env.py` at runtime using `get_settings().database_url` to respect environment variables.

---

### 7. Streamlit Frontend — `frontend/app.py` (updated)

The frontend is restructured with a two-section layout using `st.tabs` or a sidebar selector:

**Navigation:**
- Tab 1 / Sidebar option: **Phase 2: Content Planner** (default)
- Tab 2 / Sidebar option: **Phase 1: System Status** (unchanged)

**Phase 2 UI layout:**
```
🧠 AI LINKEDIN CONTENT PLANNER
───────────────────────────────
Main subject:     [text input]
Number of days:   [number input, 1-100, default 30]
Audience:         [text input]
Difficulty:       [select/text, e.g. Beginner → Intermediate]

[Generate Content Plan]  ← triggers POST /api/content-plans/generate

--- Results Table (after generation) ---
| Day | Topic | Category | Difficulty | Objective |

[🔄 Regenerate]  [💾 Save Plan]  [🗑️ Delete Plan]
```

**State management** uses `st.session_state` to hold:
- `current_plan`: the `ContentPlan` object from the last generation
- `saved_plan_id`: UUID of the last saved plan (for delete)
- `form_inputs`: last submitted form values (for regenerate)

**Plan flow:**
1. On "Generate Content Plan": POST → display table → store in `st.session_state.current_plan`
2. The generate endpoint already persists the plan, so `saved_plan_id` is available immediately.
3. "🔄 Regenerate": re-submit same form → replaces current plan (old plan remains in DB).
4. "💾 Save Plan": if auto-saved on generation, this button is informational; alternatively it can call a rename/tag endpoint in future phases. For Phase 2, the plan is saved on generation.
5. "🗑️ Delete Plan": calls DELETE `/api/content-plans/{saved_plan_id}` → clears table display.

---

## Data Models

### `content_plans` table

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID | PK, default uuid4 |
| `main_subject` | VARCHAR(500) | NOT NULL |
| `number_of_days` | INTEGER | NOT NULL |
| `audience` | VARCHAR(500) | NOT NULL |
| `difficulty` | VARCHAR(100) | NOT NULL |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() |

### `day_topics` table

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID | PK, default uuid4 |
| `plan_id` | UUID | FK → content_plans.id ON DELETE CASCADE |
| `day_number` | INTEGER | NOT NULL |
| `main_subject` | VARCHAR(500) | NOT NULL |
| `title` | VARCHAR(500) | NOT NULL |
| `short_description` | TEXT | NOT NULL |
| `difficulty` | VARCHAR(100) | NOT NULL |
| `category` | VARCHAR(200) | NOT NULL |
| `learning_objective` | TEXT | NOT NULL |

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Prompt Completeness

*For any* valid `ContentPlanRequest` (any combination of main_subject, number_of_days, audience, difficulty), the prompt string produced by `_build_prompt` must contain all required instruction elements: a directive to return only a JSON array, prohibition of markdown/commentary/think-tags, enforcement of logical progression, prohibition of duplicate topics, requirement for real-world learning objectives, and constraint on concise titles.

**Validates: Requirements 1.3, 1.4**

---

### Property 2: JSON Parsing Round-Trip

*For any* well-formed JSON array string whose elements have the DayTopic-required keys (`day_number`, `main_subject`, `title`, `short_description`, `difficulty`, `category`, `learning_objective`), calling `_parse_json_array` followed by `DayTopic(**item)` for each element should produce a list of `DayTopic` objects whose serialized representation is equivalent to the original input array.

**Validates: Requirements 1.5**

---

### Property 3: JSON Extraction From Noise

*For any* string that contains a valid DayTopic JSON array embedded within surrounding text (e.g., LLM preamble, markdown fences, `<think>` blocks), `_parse_json_array` should successfully extract and return the valid array, producing the same result as if the raw string had been the array alone.

**Validates: Requirements 1.6**

---

### Property 4: Invalid JSON Raises Descriptive Error

*For any* string that contains no valid JSON array (no `[...]` substring that parses as a list), `_parse_json_array` should raise a `ValueError` whose message includes a meaningful excerpt from the raw input rather than a bare exception.

**Validates: Requirements 1.7**

---

### Property 5: Day Number Sequential Validation

*For any* list of `DayTopic` objects where day numbers form the set `{1, 2, ..., N}` with no gaps and no duplicates, `_validate_topics` accepts the list. *For any* list where day numbers contain a duplicate or a gap (i.e., the sorted list ≠ `range(1, N+1)`), `_validate_topics` raises a `ValueError` that identifies the problematic day numbers.

**Validates: Requirements 1.8, 1.10**

---

### Property 6: Title Uniqueness Validation

*For any* list of `DayTopic` objects where all titles are distinct (case-insensitive comparison), `_validate_topics` accepts the list. *For any* list where two or more topics share the same title (case-insensitive), `_validate_topics` raises a `ValueError` that identifies the duplicate titles.

**Validates: Requirements 1.9, 1.11**

---

### Property 7: Persistence Round-Trip

*For any* valid `ContentPlanRequest` with mocked LLM returning a correctly-shaped response, after calling the generate-and-save flow, a subsequent GET to `/api/content-plans/{id}` must return a `ContentPlan` where: `main_subject`, `number_of_days`, `audience`, and `difficulty` match the request, `len(topics) == number_of_days`, and every `DayTopic` has all seven required fields populated with non-empty strings.

**Validates: Requirements 2.1, 2.2, 3.2, 10.1, 10.2**

---

### Property 8: Cascade Delete Completeness

*For any* saved content plan with N day topics, after calling DELETE `/api/content-plans/{plan_id}`, a direct database query for `DayTopicModel` records with `plan_id` equal to the deleted plan must return zero rows, and a subsequent GET to `/api/content-plans/{plan_id}` must return HTTP 404.

**Validates: Requirements 2.4, 4.1**

---

### Property 9: Request Validation — Missing Fields

*For any* POST request to `/api/content-plans/generate` that omits one or more of the required fields (`main_subject`, `number_of_days`, `audience`, `difficulty`) or supplies `null` for them, the API must return HTTP 422 without calling the Curriculum_Service.

**Validates: Requirements 5.1**

---

### Property 10: Request Validation — Out-of-Range Days

*For any* integer value of `number_of_days` that is less than 1 or greater than 100, the API must return HTTP 422 without calling the Curriculum_Service.

**Validates: Requirements 5.2**

---

### Property 11: Request Validation — Whitespace-Only Fields

*For any* string composed entirely of whitespace characters (spaces, tabs, newlines) supplied as `main_subject`, `audience`, or `difficulty`, the API must return HTTP 422 without calling the Curriculum_Service.

**Validates: Requirements 5.3, 5.4, 5.5**

---

## Error Handling

### Curriculum Service Error Handling

| Situation | Exception Raised | HTTP Mapping |
|---|---|---|
| Ollama server unreachable | `httpx.ConnectError` | 503 |
| Ollama request timeout | `httpx.TimeoutException` | 504 |
| Ollama returns non-2xx | `httpx.HTTPStatusError` | 502 |
| LLM response not parseable as JSON array | `ValueError` | 422 |
| Day numbers not sequential/duplicate | `ValueError` | 422 |
| Duplicate/near-duplicate topic titles | `ValueError` | 422 |
| Unexpected exception | `Exception` | 500 |

All errors are logged with their full traceback at `ERROR` level before the HTTP response is returned.

### API Layer Error Handling

The route handler for `POST /api/content-plans/generate` uses a structured `try/except` chain:

```python
try:
    topics = await generate_curriculum(...)
    plan = repo.save_plan(...)
    return ContentPlanResponse(success=True, message="Plan generated.", plan=...)
except httpx.ConnectError:
    raise HTTPException(503, "Ollama server is unreachable.")
except httpx.TimeoutException:
    raise HTTPException(504, "Ollama request timed out.")
except httpx.HTTPStatusError as e:
    raise HTTPException(502, f"Ollama returned an error: {e.response.status_code}")
except ValueError as e:
    raise HTTPException(422, str(e))
except Exception as e:
    logger.error("Unexpected error generating plan: %s", e, exc_info=True)
    raise HTTPException(500, "An unexpected error occurred.")
```

### Frontend Error Handling

The Streamlit frontend wraps all API calls in `try/except` and displays `st.error(...)` messages for any non-2xx response or network exception, without crashing the application or exposing stack traces to the user.

---

## Testing Strategy

### Overview

This feature involves both pure business logic (JSON parsing, validation, prompt construction) and database persistence. The testing strategy uses two complementary layers:

- **Property-based tests** (using [Hypothesis](https://hypothesis.readthedocs.io/)) for universal correctness properties across varied inputs — targeting the Curriculum_Service logic, validators, and API validation.
- **Example-based unit and integration tests** for specific scenarios, error paths, and database operations.

`pytest-asyncio` is required for testing async route handlers and the async `_call_ollama` function.

### Property-Based Tests (`pytest` + `hypothesis`)

Each property in the Correctness Properties section maps to one property-based test. Tests are tagged with feature and property references.

**Configuration:** Each test uses `@settings(max_examples=100)` and is tagged:
`# Feature: phase2-content-planner, Property N: <property_text>`

- **Property 1** (`test_prompt_completeness`): Use `@given(st.text(min_size=1), st.integers(1,100), st.text(min_size=1), st.text(min_size=1))` to generate requests; assert prompt contains all required keywords.
- **Property 2** (`test_json_parse_round_trip`): Use `@given(st.lists(st.fixed_dictionaries({...}), min_size=1))` to generate valid topic dicts; serialize to JSON, parse, re-serialize, assert equivalence.
- **Property 3** (`test_json_extraction_from_noise`): Use `@given(st.text(), valid_json_array_strategy, st.text())` to generate strings with embedded arrays; assert extraction succeeds.
- **Property 4** (`test_invalid_json_raises_error`): Use `@given(st.text())` filtered to exclude valid JSON arrays; assert `ValueError` is raised.
- **Property 5** (`test_day_number_validation`): Use `@given(valid_sequential_topics_strategy | invalid_sequential_topics_strategy)`; assert accept/reject behavior.
- **Property 6** (`test_title_uniqueness_validation`): Use `@given(unique_title_topics | duplicate_title_topics)`; assert accept/reject behavior.
- **Property 7** (`test_persistence_round_trip`): Use `@given(content_plan_request_strategy)` with mocked LLM; assert DB round-trip fidelity.
- **Property 8** (`test_cascade_delete`): Use `@given(st.integers(1, 20))` for topic count; assert zero topics after delete.
- **Property 9** (`test_missing_fields_returns_422`): Use `@given(missing_field_request_strategy)`; assert 422.
- **Property 10** (`test_out_of_range_days_returns_422`): Use `@given(st.integers().filter(lambda x: x < 1 or x > 100))`; assert 422.
- **Property 11** (`test_whitespace_fields_returns_422`): Use `@given(whitespace_strategy, field_choice_strategy)`; assert 422.

### Example-Based Tests (`pytest`)

| Test | Description |
|---|---|
| `test_ollama_call_parameters` | Mock httpx, assert POST to correct URL with `stream=False` and `qwen3:4b` |
| `test_ollama_unreachable_returns_503` | Mock httpx raising `ConnectError`, assert 503 response |
| `test_ollama_timeout_returns_504` | Mock httpx raising `TimeoutException`, assert 504 response |
| `test_valid_llm_response_creates_plan` | Mock LLM returning valid JSON, assert plan created and returned |
| `test_invalid_llm_response_returns_422` | Mock LLM returning garbage text, assert 422 |
| `test_duplicate_day_numbers_returns_422` | Mock LLM returning duplicate day_number, assert 422 |
| `test_duplicate_titles_returns_422` | Mock LLM returning duplicate titles, assert 422 |
| `test_list_plans_returns_all` | Save 3 plans, GET /, assert 3 summaries returned |
| `test_get_nonexistent_plan_returns_404` | GET with random UUID, assert 404 |
| `test_delete_nonexistent_plan_returns_404` | DELETE with random UUID, assert 404 |
| `test_phase1_health_still_returns_200` | GET /health, assert 200 + `{"status": "ok"}` |
| `test_created_at_is_populated` | Save plan, assert `created_at` is a datetime |

### Test File

All Phase 2 tests reside in `backend/tests/test_content_plans.py`.
Phase 1 tests remain untouched in `backend/tests/test_health.py`.

### New Dependency

Add to `requirements.txt`:
```
pytest-asyncio==0.24.0
hypothesis==6.115.3
```
