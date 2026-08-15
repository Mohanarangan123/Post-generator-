# Implementation Plan: Phase 4 — Infographic Generation

## Overview

This implementation plan covers the full Phase 4 infographic generation pipeline, from the `ImageModel` ORM and Alembic migration through the API endpoint, Playwright renderer, property-based tests, and Streamlit UI additions. Tasks are ordered for incremental, verifiable progress with two explicit checkpoints (tasks 12 and 15) to catch regressions.

## Task Dependency Graph

```json
{
  "waves": [
    {"wave": 1, "tasks": ["1"]},
    {"wave": 2, "tasks": ["2", "3", "10"]},
    {"wave": 3, "tasks": ["4", "7"]},
    {"wave": 4, "tasks": ["5"]},
    {"wave": 5, "tasks": ["6"]},
    {"wave": 6, "tasks": ["8"]},
    {"wave": 7, "tasks": ["9"]},
    {"wave": 8, "tasks": ["11"]},
    {"wave": 9, "tasks": ["12"]},
    {"wave": 10, "tasks": ["13"]},
    {"wave": 11, "tasks": ["14"]},
    {"wave": 12, "tasks": ["15"]}
  ]
}
```

## Tasks

- [x] 1. ImageModel ORM, ImageStatus enum, PostModel relationship, and models/__init__.py update
  - Create `backend/app/models/image.py` with `ImageStatus(str, enum.Enum)` having values `PENDING`, `GENERATING`, `COMPLETED`, `FAILED`
  - Create `ImageModel(Base)` mapped to table `images` with columns: `id` (Uuid PK, default uuid4), `post_id` (Uuid FK → `posts.id` CASCADE DELETE), `provider` (String(100), non-null), `prompt` (Text, non-null), `visual_spec` (JSON, non-null), `file_path` (String(500), nullable), `width` (Integer, nullable), `height` (Integer, nullable), `status` (String(50), non-null, default `"PENDING"`), `created_at` (DateTime(timezone=True), non-null)
  - Use `Mapped`, `mapped_column`, and `Uuid(as_uuid=True)` throughout — never `postgresql.UUID`
  - Add `post: Mapped["PostModel"]` relationship with `back_populates="images"` on `ImageModel`
  - Add `images: Mapped[list["ImageModel"]]` relationship to `PostModel` in `backend/app/models/post.py` with `back_populates="post"` and `cascade="all, delete-orphan"` — this is the only permitted change to an existing model file
  - Update `backend/app/models/__init__.py` to import `ImageModel` and `ImageStatus`
  - **Requirement refs:** 3.1, 3.2, 3.3, 12.1, 12.2, 12.3

- [x] 2. Alembic migration 0003 — add images table
  - Create `backend/alembic/versions/0003_add_images_table.py`
  - Set `revision = "0003"`, `down_revision = "0002"`, `branch_labels = None`, `depends_on = None`
  - `upgrade()`: call `op.create_table("images", ...)` with all columns matching `ImageModel` (use `sa.Uuid(as_uuid=True)`, `sa.Text()`, `sa.JSON()`, `sa.String()`, `sa.Integer()`, `sa.DateTime(timezone=True)`), add FK constraint to `posts.id` with `ondelete="CASCADE"`, add PK constraint; then call `op.create_index("ix_images_post_id", "images", ["post_id"])`
  - `downgrade()`: call `op.drop_index("ix_images_post_id", table_name="images")` then `op.drop_table("images")`
  - Do NOT alter any existing table in this migration
  - **Requirement refs:** 3.4, 3.5, 3.6, 12.6

- [x] 3. VisualSpec, ImageRead, and ImageResponse Pydantic schemas
  - Create `backend/app/schemas/image.py`
  - `VisualSpec(BaseModel)`: fields `day_number: int = Field(..., ge=1)`, `title: str = Field(..., min_length=1)`, `subtitle: str`, `visual_concept: str = Field(..., min_length=1)`, `diagram_type: Literal["flowchart","hierarchy","comparison","timeline","list"]`, `diagram_nodes: list[str] = Field(..., min_length=1, max_length=10)`, `key_points: list[str] = Field(..., min_length=3, max_length=5)`, `style: Literal["dark-tech","light-minimal","blue-gradient"]`, `aspect_ratio: Literal["1:1","4:5","16:9"]`
  - `ImageRead(BaseModel)`: fields `id`, `post_id`, `provider`, `prompt`, `visual_spec` (dict), `file_path` (Optional[str]), `width` (Optional[int]), `height` (Optional[int]), `status`, `created_at`; set `model_config = {"from_attributes": True}`
  - `ImageResponse(BaseModel)`: fields `success: bool` plus all `ImageRead` fields (flattened — no nested `image` key)
  - Update `backend/app/schemas/__init__.py` to import the new schemas
  - **Requirement refs:** 1.1–1.8, 8.6

- [x] 4. ImageProvider ABC, MockImageProvider, and HuggingFaceImageProvider
  - Create `backend/app/services/image_providers.py`
  - Define `ImageProviderError(Exception)` custom exception
  - Define `ImageProvider(ABC)` with abstract async method `generate(self, prompt: str) -> bytes`
  - `MockImageProvider(ImageProvider)`: implement `generate` returning deterministic 1080×1080 solid-color PNG bytes using `PIL.Image.new("RGB", (1080, 1080), color=(30, 58, 95))` saved to an in-memory `io.BytesIO`; no random seed; same prompt always returns same bytes; no network calls
  - `HuggingFaceImageProvider(ImageProvider)`: `__init__(self, token: str, model_id: str)`; `generate` calls the HF Inference API using `httpx.AsyncClient` with a 60-second timeout and bearer token; raise `ImageProviderError` (with descriptive message) if `token` is empty before making any call, if response is non-2xx (include status code in message), or if the request times out
  - `get_image_provider(settings) -> ImageProvider` factory: returns `MockImageProvider()` when `settings.image_provider == "mock"` or any unrecognized value; returns `HuggingFaceImageProvider(settings.hf_token, settings.hf_image_model)` when `settings.image_provider == "huggingface"` (raises `ImageProviderError` immediately if token is empty)
  - **Requirement refs:** 2.1–2.11

- [x] 5. HTML/CSS template service
  - Create `backend/app/services/image_template.py`
  - Define `ASPECT_RATIO_DIMS: dict[str, tuple[int, int]] = {"1:1": (1080, 1080), "4:5": (1080, 1350), "16:9": (1920, 1080)}`
  - `_get_style_css(style: str, w: int, h: int) -> str`: return CSS string where `dark-tech` uses `background: #0a0a1a; color: #e0e0ff`, `light-minimal` uses `background: #ffffff; color: #1a1a1a`, `blue-gradient` uses `background: linear-gradient(135deg, #1e3a5f, #4a90d9); color: #ffffff`; root `body` sets `width: {w}px; height: {h}px; margin: 0; font-family: 'Segoe UI', sans-serif; overflow: hidden`
  - `build_html(visual_spec: VisualSpec, bg_bytes: bytes) -> str`: Base64-encode `bg_bytes`, format `day_number` as zero-padded 2-digit string, join `key_points` as `<li>` elements, return complete `<!DOCTYPE html>` document with container, `.day-header` (`DAY XX`), `<h1 class="title">`, `.visual-area` with `<img src="data:image/png;base64,...">`, `<ul class="key-points">`, and `.footer` containing `#LearnWithAI`
  - Return value must contain `<!DOCTYPE html>`, the DAY header, `visual_spec.title`, and all `key_points` items
  - **Requirement refs:** 5.1–5.10

- [x] 6. Playwright renderer service
  - Create `backend/app/services/image_renderer.py`
  - Define `RenderingError(Exception)` custom exception
  - `render_html_to_png(html: str, output_path: Path, width: int, height: int) -> Path` (async): use `async with async_playwright() as p`, launch headless Chromium, create page with `viewport={"width": width, "height": height}`, call `page.set_content(html, wait_until="networkidle")`, call `page.screenshot(path=str(output_path), full_page=False)`, close browser, return `output_path`
  - Wrap any `Exception` from Playwright in `RenderingError` with a descriptive message
  - **Requirement refs:** 6.1–6.6

- [x] 7. VisualSpec generation service (Qwen3 via Ollama)
  - Create `backend/app/services/visual_spec_service.py`
  - Define `VisualSpecGenerationError(Exception)` custom exception
  - `_build_visual_spec_prompt(post: PostModel, topic: DayTopicModel) -> str`: construct a prompt that includes `post.content`, `topic.title`, `topic.day_number`, `topic.main_subject`, `topic.category`, and `topic.difficulty`; instruct Qwen3 to respond with only valid JSON matching the `VisualSpec` schema, no prose, no markdown fences, no `<think>` blocks; handle any null fields gracefully by including only available fields
  - `_strip_think_blocks(raw: str) -> str`: apply `re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()`
  - `_call_ollama(prompt: str) -> str` (async): POST to `{settings.ollama_base_url}/api/generate` with `model=settings.ollama_model`, `stream=False`; catch `httpx.ConnectError` and wrap in `VisualSpecGenerationError("Ollama is unreachable: ...")`; return `response.json()["response"]`
  - `_parse_visual_spec(text: str) -> VisualSpec`: parse JSON from `text`; catch `json.JSONDecodeError` and `ValidationError` and raise `VisualSpecGenerationError`; strip any residual markdown code fences before parsing
  - `generate_visual_spec(post: PostModel, topic: DayTopicModel) -> VisualSpec` (async): compose the four helpers in order
  - **Requirement refs:** 4.1–4.7

- [x] 8. ImageRepository CRUD
  - Create `backend/app/services/image_repository.py`
  - `ImageRepository.__init__(self, db: Session)`
  - `create(self, post_id: UUID, provider: str, prompt: str, visual_spec: dict) -> ImageModel`: instantiate `ImageModel` with `id=uuid.uuid4()`, `status=ImageStatus.PENDING`, `created_at=datetime.now(timezone.utc)` plus all passed fields; add, commit, refresh, return
  - `update_status(self, image_id: UUID, status: str, file_path: str | None = None, width: int | None = None, height: int | None = None, visual_spec: dict | None = None) -> ImageModel`: fetch by id, update `status`; conditionally update `file_path`, `width`, `height`, `visual_spec` when not None; commit, refresh, return
  - `get(self, image_id: UUID) -> ImageModel | None`: query by id
  - `get_by_post(self, post_id: UUID) -> ImageModel | None`: query by `post_id`, order by `created_at` desc, return first
  - **Requirement refs:** 7.1–7.6

- [x] 9. image_service pipeline orchestrator
  - Create `backend/app/services/image_service.py`
  - Import and use: `ImageRepository`, `generate_visual_spec`, `get_image_provider`, `build_html`, `render_html_to_png`, `ASPECT_RATIO_DIMS`, `ImageStatus`, `PostModel` (with `joinedload(PostModel.day_topic)`)
  - `run_pipeline(post_id: UUID, db: Session) -> ImageModel` (async):
    1. Load `PostModel` with joined `day_topic` (caller verifies existence before calling)
    2. `repo.create(post_id, provider="", prompt="", visual_spec={})` → `image`
    3. Try block: call `generate_visual_spec(post, topic)` → `visual_spec`
    4. `repo.update_status(image.id, ImageStatus.GENERATING)`
    5. `provider = get_image_provider(settings)`; `bg_bytes = await provider.generate(visual_spec.visual_concept)`
    6. `html = build_html(visual_spec, bg_bytes)`
    7. Resolve dims from `ASPECT_RATIO_DIMS[visual_spec.aspect_ratio]`; `output_dir.mkdir(parents=True, exist_ok=True)`; build `output_path = output_dir / f"{post_id}_{ts}.png"`
    8. `await render_html_to_png(html, output_path, w, h)`
    9. `repo.update_status(image.id, ImageStatus.COMPLETED, file_path=str(output_path), width=w, height=h, visual_spec=visual_spec.model_dump())`; set `image.provider = type(provider).__name__`; set `image.prompt = visual_spec.visual_concept`; commit and refresh
    10. Except `Exception`: `repo.update_status(image.id, ImageStatus.FAILED)`; refresh; do NOT re-raise
  - Return `image` in all cases (success or failure)
  - **Requirement refs:** 4.1–4.6, 5.1–5.10, 6.1–6.5, 7.1–7.6

- [x] 10. Settings extension and .env.example update
  - Add four fields to `Settings` in `backend/app/core/config.py`:
    - `image_provider: str = "mock"`
    - `hf_token: str = ""`
    - `hf_image_model: str = "stabilityai/stable-diffusion-xl-base-1.0"`
    - `image_output_dir: str = "images"`
  - Do not modify any existing field or `SettingsConfigDict`
  - Update `.env.example` to document the four new variables with their default values and brief comments
  - **Requirement refs:** 9.1–9.4

- [x] 11. images API router and app/main.py registration
  - Create `backend/app/api/routes/images.py` with `router = APIRouter(prefix="/api/images", tags=["images"])`
  - `POST /generate/{post_id}` endpoint: accept `post_id: UUID`, inject `db: Session = Depends(get_db)`; query `PostModel` by id — raise `HTTPException(status_code=404, detail=f"Post {post_id} not found.")` if absent; call `await run_pipeline(post_id, db)` → `image`; return `ImageResponse(success=(image.status == ImageStatus.COMPLETED), **ImageRead.model_validate(image).model_dump())`
  - Register in `backend/app/main.py`: add `from app.api.routes.images import router as images_router` and `app.include_router(images_router)` — this is the only permitted change to `main.py`
  - **Requirement refs:** 8.1–8.7

- [x] 12. Checkpoint — run existing 54 tests (must all pass, zero new tests yet)
  - Run `pytest backend/ -x -q --ignore=backend/tests/test_images.py`
  - All 54 existing tests must pass before proceeding
  - If any test fails, diagnose and fix the regression before continuing
  - **Requirement refs:** 11.12, 12.5

- [x] 13. Write test_images.py — full test suite
  - Create `backend/tests/test_images.py`
  - Reuse the same `db_engine`, `db_session`, `client` fixture pattern from `test_posts.py`; add helper `make_post(db_session, topic)` that creates a `PostModel` with status `DRAFT`
  - **Unit tests (example-based):**
    - `test_valid_visual_spec_construction` — build a `VisualSpec` with all valid fields, assert `model_dump()` contains exactly the expected keys; **Req 1.1, 1.2**
    - `test_visual_spec_invalid_too_few_key_points` — assert `ValidationError` for `key_points` with 2 items; **Req 1.3**
    - `test_visual_spec_invalid_too_many_key_points` — assert `ValidationError` for `key_points` with 6 items; **Req 1.3**
    - `test_visual_spec_invalid_day_number` — assert `ValidationError` for `day_number=0`; **Req 1.4**
    - `test_visual_spec_invalid_empty_title` — assert `ValidationError` for `title=""`; **Req 1.6**
    - `test_mock_provider_returns_png_magic_bytes` — call `asyncio.run(MockImageProvider().generate("test prompt"))`, assert result starts with `b"\x89PNG\r\n\x1a\n"`; **Req 2.2, 2.4**
    - `test_html_template_contains_required_elements` — call `build_html(valid_spec, b"")`, assert string contains `"DAY 01"`, `valid_spec.title`, and each item from `valid_spec.key_points`; **Req 5.1, 5.2, 5.4**
    - `test_image_model_persistence_round_trip` — create `ImageModel` record in SQLite, retrieve by id, assert all fields equal; **Req 3.1, 3.7**
    - `test_pipeline_failure_when_provider_raises` — mock `MockImageProvider.generate` to raise `ImageProviderError("test error")`; call `run_pipeline`; assert returned `ImageModel.status == "FAILED"`; **Req 7.4**
    - `test_generate_image_api_happy_path` — mock `visual_spec_service._call_ollama` to return valid `VisualSpec` JSON string; mock `image_renderer.render_html_to_png` to write a stub PNG and return the path; call `POST /api/images/generate/{post_id}` via `TestClient`; assert HTTP 200, `success=True`, `status="COMPLETED"`, `file_path` not null; **Req 8.1, 8.3**
    - `test_generate_image_api_nonexistent_post` — call `POST /api/images/generate/{random_uuid}`; assert HTTP 404; **Req 8.2**
  - **Property-based tests (Hypothesis `@given`, `@h_settings(max_examples=100)`):**
    - `test_visual_spec_round_trip` — tagged `# Feature: phase4-infographic-generation, Property 1: VisualSpec round-trip`; use `st.builds(VisualSpec, ...)` with all constrained fields using appropriate `st.integers`, `st.text`, `st.sampled_from`, `st.lists` strategies; assert `VisualSpec.model_validate(v.model_dump()) == v`; **Req 1.8, 11.3**
    - `test_mock_provider_returns_valid_png` — tagged `# Feature: phase4-infographic-generation, Property 2: MockImageProvider returns valid PNG for any non-empty prompt`; `@given(prompt=st.text(min_size=1, max_size=500))`; assert magic bytes and determinism (call twice, compare); **Req 2.2, 2.3, 11.4, 11.6 (via pbt)**
    - `test_html_template_contains_title` — tagged `# Feature: phase4-infographic-generation, Property 3: HTML template always contains title`; `@given` valid `VisualSpec`; call `build_html(v, b"")`; assert `v.title in result`; **Req 5.2, 5.9, 11.6**
  - **Integration test (Playwright, `@pytest.mark.integration`):**
    - `test_playwright_renders_correct_dimensions` — `pytest.importorskip("playwright")`; call `asyncio.run(render_html_to_png(html, tmp_path / "out.png", 1080, 1080))`; open with `PIL.Image.open`; assert `img.size == (1080, 1080)`; **Req 6.1, 6.2, 11.7**
  - **Requirement refs:** 11.1–11.12

- [x] 14. Streamlit Content Calendar tab — add visual buttons
  - Modify `frontend/app.py` inside `render_content_calendar()` only — do not alter Tab 1, Tab 2, or any other section
  - After loading `posts_by_topic`, also load image data: call `GET /api/images/by-post/{post_id}` if that endpoint exists, or store image responses in `st.session_state` keyed by post id after generate/regenerate calls
  - In the per-row `col_actions` section, add three additional buttons: `"Generate Visual"` (key `f"img_gen_{topic_id}"`), `"Regenerate Visual"` (key `f"img_regen_{topic_id}"`), `"View Infographic"` (key `f"img_view_{topic_id}"`)
  - `"Generate Visual"` handler: `post_json(f"{BACKEND_URL}/api/images/generate/{post['id']}", {}, timeout=GENERATE_TIMEOUT_SECONDS)`; store response in `st.session_state[f"img_{post_id}"]`; display `st.success(...)` if `resp_data["success"]` else `st.error(...)`
  - `"Regenerate Visual"` handler: same call as Generate Visual; overwrites prior session state; display appropriate message
  - `"View Infographic"` handler: look up `st.session_state[f"img_{post_id}"]`; if `status == "COMPLETED"` and file path exists: display `st.text(post["content"])`, `st.expander("VisualSpec")` containing `st.json(img_data["visual_spec"])`, and `st.image(img_data["file_path"])`; otherwise: `st.info("No completed infographic yet. Click 'Generate Visual' to create one.")`
  - **Requirement refs:** 10.1–10.6

- [x] 15. Final checkpoint — run complete test suite
  - Run `pytest backend/ -q` — all Phase 1–3 tests plus all Phase 4 tests must pass
  - Run `pytest backend/tests/test_images.py -k "round_trip or valid_png or contains_title" -q` to confirm property tests pass individually
  - Run `pytest backend/ -m integration -q` if Playwright is installed
  - Zero failures required; the feature is complete when this checkpoint passes
  - **Requirement refs:** 11.12, 12.5

## Notes

- All new UUID columns use `Uuid(as_uuid=True)` (dialect-agnostic, SQLite-compatible). Never use `postgresql.UUID`.
- `MockImageProvider` is the default for all tests and the default production configuration (`IMAGE_PROVIDER=mock`). No Hugging Face token or GPU is required to run the system.
- The Playwright integration test (`test_playwright_renders_correct_dimensions`) is skipped if `playwright` is not installed. Use `pytest.importorskip("playwright")` at the top of the test function.
- The `run_pipeline` function never re-raises exceptions — it catches all of them, marks the `ImageModel` as `FAILED`, and returns the model. The router translates `status == FAILED` into `success=False` in the `ImageResponse`.
- Phase 4 additions are strictly additive. The only permitted edits to pre-existing files are: `PostModel` (add `images` relationship), `Settings` (add 4 fields), `app/main.py` (register images router), `models/__init__.py` (import ImageModel), `schemas/__init__.py` (import new schemas), and `frontend/app.py` (add buttons inside `render_content_calendar`).
- Property-based tests use `asyncio.run(...)` to call async provider methods synchronously within Hypothesis `@given` blocks, consistent with the patterns in `test_posts.py`.
