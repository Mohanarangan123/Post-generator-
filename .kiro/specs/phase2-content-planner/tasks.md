# Implementation Plan: Phase 2 — AI-Powered LinkedIn Content Planner

## Overview

Implements the full Phase 2 feature on top of the Phase 1 foundation: Pydantic schemas, SQLAlchemy models, Alembic migration, curriculum generation service (Ollama + Qwen3 4B), FastAPI CRUD endpoints, Streamlit UI, and a comprehensive test suite.

## Tasks

- [x] 1. Add Pydantic schemas for content plans
  - Create `backend/app/schemas/content_plan.py` with `DayTopic`, `ContentPlanRequest`, `ContentPlan`, `ContentPlanResponse`, and `PlanSummary` models
  - `DayTopic`: fields day_number (int), main_subject (str), title (str), short_description (str), difficulty (str), category (str), learning_objective (str)
  - `ContentPlanRequest`: main_subject/audience/difficulty non-empty with strip_whitespace, number_of_days Field(ge=1, le=100)
  - `ContentPlan`: optional id (UUID), main_subject, number_of_days, audience, difficulty, topics (list[DayTopic]), optional created_at; model_config from_attributes=True
  - `ContentPlanResponse`: success (bool), message (str), plan (Optional[ContentPlan])
  - `PlanSummary`: id, main_subject, number_of_days, created_at; model_config from_attributes=True

- [x] 2. Add SQLAlchemy ORM models
  - Create `backend/app/models/content_plan.py` with `ContentPlanModel` and `DayTopicModel`
  - `ContentPlanModel`: UUID PK default uuid4, main_subject VARCHAR(500), number_of_days INTEGER, audience VARCHAR(500), difficulty VARCHAR(100), created_at TIMESTAMPTZ default utcnow, relationship to DayTopicModel with cascade="all, delete-orphan"
  - `DayTopicModel`: UUID PK, plan_id FK → content_plans.id ON DELETE CASCADE, day_number INTEGER, main_subject VARCHAR(500), title VARCHAR(500), short_description TEXT, difficulty VARCHAR(100), category VARCHAR(200), learning_objective TEXT
  - Update `backend/app/models/__init__.py` to import both models so Alembic can discover them

- [x] 3. Initialize Alembic and create initial migration
  - Create `backend/alembic.ini` with script_location=alembic; sqlalchemy.url will be overridden at runtime
  - Create `backend/alembic/env.py` importing Base from app.db.base and all models; override DB URL from get_settings() at runtime; configure both online and offline modes
  - Create `backend/alembic/script.py.mako` standard template
  - Create initial migration `backend/alembic/versions/0001_initial_content_plan_tables.py` that creates content_plans and day_topics tables with all columns, PK, FK, and indexes

- [x] 4. Implement the Curriculum Service
  - Create `backend/app/services/curriculum_service.py`
  - Implement `_build_prompt(main_subject, number_of_days, audience, difficulty) -> str` with all required directives: JSON-only output, no markdown/think-tags, logical progression, no duplicates, real-world objectives, concise titles
  - Implement async `_call_ollama(prompt) -> str` using httpx.AsyncClient with 120s timeout, POST to `{OLLAMA_BASE_URL}/api/generate` with model, prompt, stream=False; extract data["response"]
  - Implement `_parse_json_array(raw) -> list[dict]`: strip `<think>.*</think>` with re.DOTALL, strip markdown fences, try direct json.loads, extract first `[`...`]` substring on failure, raise descriptive ValueError if still unparseable
  - Implement `_validate_topics(topics, expected_count)`: check sorted day_numbers == list(range(1, N+1)); check all titles unique case-insensitively; raise descriptive ValueError on violations
  - Implement public async `generate_curriculum(main_subject, number_of_days, audience, difficulty) -> list[DayTopic]` orchestrating build_prompt → call_ollama → parse_json_array → DayTopic(**item) for each → validate_topics

- [x] 5. Implement the Plan Repository
  - Create `backend/app/services/content_plan_repository.py` with `ContentPlanRepository(db: Session)`
  - `save_plan(request, topics)`: create ContentPlanModel, create one DayTopicModel per topic, db.add/commit/refresh, return the ContentPlanModel
  - `list_plans()`: query all ContentPlanModel ordered by created_at desc
  - `get_plan(plan_id)`: query ContentPlanModel by id with joinedload on topics, return or None
  - `delete_plan(plan_id)`: load plan, db.delete, commit, return True; return False if not found

- [x] 6. Implement the API router and register it
  - Create `backend/app/api/routes/content_plans.py` with `router = APIRouter(prefix="/api/content-plans", tags=["content-plans"])`
  - `POST /generate`: validate ContentPlanRequest, call generate_curriculum (async), save via repository, return ContentPlanResponse(success=True); catch httpx.ConnectError→HTTPException(503), TimeoutException→504, HTTPStatusError→502, ValueError→422, Exception→500
  - `GET /`: return list[PlanSummary] from repository
  - `GET /{plan_id}`: return ContentPlanResponse or HTTPException(404)
  - `DELETE /{plan_id}`: call delete_plan; return {"message": "deleted"} or HTTPException(404)
  - Register router in `backend/app/main.py`: add import and `app.include_router(content_plans_router)`

- [x] 7. Update the Streamlit frontend
  - Restructure `frontend/app.py` using `st.tabs(["📅 Content Planner", "📊 System Status"])`
  - Tab 1 — Content Planner: form with main_subject text_input, number_of_days number_input (1–100, default 30), audience text_input, difficulty selectbox with options ("Beginner", "Beginner → Intermediate", "Intermediate", "Intermediate → Advanced", "Advanced")
  - "Generate Content Plan" button with st.spinner → POST to `/api/content-plans/generate` → store result in st.session_state (current_plan, saved_plan_id, form_inputs)
  - Display results as st.dataframe with columns: Day, Topic, Category, Difficulty, Objective
  - "🔄 Regenerate" button: re-submit same form_inputs
  - "🗑️ Delete Plan" button: DELETE `/api/content-plans/{saved_plan_id}` → clear session state → st.success
  - All API errors displayed via st.error() without crashing
  - Tab 2 — System Status: move existing Phase 1 dashboard content here unchanged

- [x] 8. Add new dependencies to requirements.txt
  - Add `pytest-asyncio==0.24.0` to `requirements.txt`
  - Add `hypothesis==6.115.3` to `requirements.txt`

- [x] 9. Write tests for Phase 2
  - Create `backend/tests/test_content_plans.py`
  - Property test `test_prompt_completeness`: @given(text, int 1–100, text, text) → assert prompt contains all required directive keywords
  - Property test `test_json_parse_round_trip`: @given valid topic dicts → serialize → parse → re-serialize → equivalent
  - Property test `test_json_extraction_from_noise`: @given prefix_text, valid JSON array, suffix_text → extraction succeeds
  - Property test `test_invalid_json_raises_error`: @given text filtered to exclude valid JSON arrays → ValueError raised
  - Property test `test_day_number_validation`: sequential topics → accepted; non-sequential or duplicate → ValueError
  - Property test `test_title_uniqueness_validation`: unique titles → accepted; duplicates → ValueError
  - Property test `test_missing_fields_returns_422`: requests missing required fields → HTTP 422
  - Property test `test_out_of_range_days_returns_422`: number_of_days outside 1–100 → HTTP 422
  - Property test `test_whitespace_fields_returns_422`: whitespace-only string fields → HTTP 422
  - Example test `test_valid_llm_response_creates_plan`: mock LLM valid JSON → 200, plan in response, persisted in DB
  - Example test `test_invalid_llm_response_returns_422`: mock LLM garbage text → 422
  - Example test `test_duplicate_day_numbers_returns_422`: mock LLM duplicate day_number → 422
  - Example test `test_duplicate_titles_returns_422`: mock LLM duplicate titles → 422
  - Example test `test_ollama_unreachable_returns_503`: mock httpx ConnectError → 503
  - Example test `test_ollama_timeout_returns_504`: mock httpx TimeoutException → 504
  - Example test `test_persistence_round_trip`: generate → GET by id → all fields match
  - Example test `test_cascade_delete_removes_topics`: generate → DELETE → GET 404, topics gone
  - Example test `test_get_nonexistent_plan_returns_404`: GET random UUID → 404
  - Example test `test_list_plans_returns_all`: save 3 → GET / → 3 summaries
  - Example test `test_phase1_health_still_returns_200`: GET /health → 200 + {"status": "ok"}
  - _dependencies: 1, 2, 4, 5, 6, 8_

- [x] 10. Run all tests and fix errors
  - Install dependencies: `pip install pytest-asyncio==0.24.0 hypothesis==6.115.3` (or from requirements.txt)
  - Run `pytest` in `backend/` and fix all failures until the full suite passes (including Phase 1 tests)
  - _dependencies: 1, 2, 3, 4, 5, 6, 7, 8, 9_

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["1", "2", "8"]},
    {"wave": 2, "tasks": ["3", "4"]},
    {"wave": 3, "tasks": ["5"]},
    {"wave": 4, "tasks": ["6", "7"]},
    {"wave": 5, "tasks": ["9"]},
    {"wave": 6, "tasks": ["10"]}
  ]
}
```

## Notes

- Do NOT modify any Phase 1 files except `backend/app/main.py` (to register the new router) and `requirements.txt` (to add new packages).
- Alembic env.py must override `sqlalchemy.url` from `get_settings().database_url` at runtime so `.env` values are respected.
- The Ollama call must be non-streaming (`stream: false`) and use a 120-second timeout.
- The `_parse_json_array` function must strip `<think>` blocks before attempting JSON extraction (Qwen3 thinking mode produces these).
- Tests use an in-memory SQLite DB or a test PostgreSQL DB; mock httpx for all Ollama calls — never call the real Ollama in tests.
- pytest.ini in `backend/` should be updated to add `asyncio_mode = auto` for pytest-asyncio.
