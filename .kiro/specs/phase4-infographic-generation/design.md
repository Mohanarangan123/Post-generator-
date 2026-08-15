# Design Document — Phase 4: Infographic Generation

## Overview

Phase 4 adds an automated infographic pipeline to the existing LinkedIn AI Content Generator. For each `PostModel` already generated in Phase 3, users can trigger the creation of a professional educational PNG infographic without leaving the Streamlit interface.

The pipeline flows through five distinct stages per post:

1. **VisualSpec generation** — Qwen3 (via Ollama) analyzes the post and its `DayTopicModel` metadata, then returns a structured JSON `VisualSpec` describing the intended layout, style, and content.
2. **Background image generation** — An `ImageProvider` produces PNG bytes representing the visual background. The pluggable interface allows swapping `MockImageProvider` (deterministic, no network, default) for `HuggingFaceImageProvider` (cloud API).
3. **HTML/CSS composition** — An f-string template embeds all `VisualSpec` fields and the Base64-encoded background into a self-contained HTML document.
4. **Playwright rendering** — Headless Chromium takes a screenshot of the HTML at the target resolution, producing the final PNG file.
5. **Persistence** — An `ImageModel` record is created at pipeline start (status `PENDING`) and updated through `GENERATING` → `COMPLETED` (or `FAILED` on any exception). The file path, dimensions, and serialized `VisualSpec` are stored.

The endpoint `POST /api/images/generate/{post_id}` triggers the full pipeline and returns an `ImageResponse`. The Streamlit Content Calendar tab gains three per-row buttons: **Generate Visual**, **Regenerate Visual**, and **View Infographic**.

All GPU-dependent image-generation models (FLUX, Stable Diffusion) are explicitly out of scope. The system runs entirely CPU-bound in its default configuration.

---

## Architecture

```
Streamlit (frontend/app.py)
        │
        │  POST /api/images/generate/{post_id}
        ▼
┌─────────────────────────────┐
│  FastAPI images Router      │  app/api/routes/images.py
│  POST /api/images/generate  │
└──────────┬──────────────────┘
           │  run_pipeline(post_id, db)
           ▼
┌─────────────────────────────┐
│  image_service.py           │  orchestrator
│  run_pipeline()             │
└──┬────┬────┬────┬───────────┘
   │    │    │    │
   │    │    │    └─ ImageRepository (CRUD)
   │    │    └────── image_renderer.py (Playwright)
   │    └─────────── image_template.py (HTML builder)
   └──────────────── visual_spec_service.py (Qwen3 call)
                     image_providers.py (MockImageProvider / HuggingFaceImageProvider)
```

The pipeline orchestrator (`image_service.py`) is the only module that touches all other services. Each service module has a single, focused responsibility with no cross-dependencies between them. This mirrors the patterns established in Phases 1–3.

### Layering

```
API Layer          → images.py router
Service Layer      → image_service, visual_spec_service, image_providers,
                     image_template, image_renderer
Repository Layer   → image_repository
Model Layer        → ImageModel, ImageStatus (ORM + enum)
Schema Layer       → VisualSpec, ImageRead, ImageResponse (Pydantic)
Config Layer       → Settings (four new fields)
```

---

## Components and Interfaces

### `ImageStatus` (enum, `app/models/image.py`)

```python
class ImageStatus(str, enum.Enum):
    PENDING    = "PENDING"
    GENERATING = "GENERATING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"
```

### `ImageModel` (ORM, `app/models/image.py`)

Maps to the `images` table. Key columns:

| Column | Type | Notes |
|---|---|---|
| `id` | `Uuid(as_uuid=True)` PK | default `uuid.uuid4` |
| `post_id` | `Uuid` FK → `posts.id` CASCADE | non-null |
| `provider` | `String(100)` | class name of ImageProvider used |
| `prompt` | `Text` | `visual_concept` sent to provider |
| `visual_spec` | `JSON` | serialized VisualSpec dict |
| `file_path` | `String(500)` | nullable until COMPLETED |
| `width` | `Integer` | nullable until COMPLETED |
| `height` | `Integer` | nullable until COMPLETED |
| `status` | `String(50)` | default `"PENDING"` |
| `created_at` | `DateTime(timezone=True)` | non-null |

Uses `Uuid(as_uuid=True)` throughout — never `postgresql.UUID` — for SQLite compatibility in tests.

`PostModel.images` relationship added in `app/models/post.py`:

```python
images: Mapped[list["ImageModel"]] = relationship(
    "ImageModel",
    back_populates="post",
    cascade="all, delete-orphan",
)
```

### `VisualSpec` (Pydantic, `app/schemas/image.py`)

```python
class VisualSpec(BaseModel):
    day_number:    int   = Field(..., ge=1)
    title:         str   = Field(..., min_length=1)
    subtitle:      str
    visual_concept: str  = Field(..., min_length=1)
    diagram_type:  Literal["flowchart", "hierarchy", "comparison", "timeline", "list"]
    diagram_nodes: list[str] = Field(..., min_length=1, max_length=10)
    key_points:    list[str] = Field(..., min_length=3, max_length=5)
    style:         Literal["dark-tech", "light-minimal", "blue-gradient"]
    aspect_ratio:  Literal["1:1", "4:5", "16:9"]
```

Pydantic v2 constraints enforce all acceptance criteria at construction time.

### `ImageRead` / `ImageResponse` (Pydantic, `app/schemas/image.py`)

```python
class ImageRead(BaseModel):
    id:          UUID
    post_id:     UUID
    provider:    str
    prompt:      str
    visual_spec: dict
    file_path:   Optional[str]
    width:       Optional[int]
    height:      Optional[int]
    status:      str
    created_at:  datetime
    model_config = {"from_attributes": True}

class ImageResponse(BaseModel):
    success:    bool
    id:         UUID
    post_id:    UUID
    provider:   str
    prompt:     str
    visual_spec: dict
    file_path:  Optional[str]
    width:      Optional[int]
    height:     Optional[int]
    status:     str
    created_at: datetime
```

`ImageResponse` flattens the model fields directly (no nested `image` key) to simplify frontend consumption.

### `ImageProvider` ABC (`app/services/image_providers.py`)

```python
from abc import ABC, abstractmethod

class ImageProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> bytes: ...

class MockImageProvider(ImageProvider):
    async def generate(self, prompt: str) -> bytes:
        # Returns deterministic 1080×1080 solid-blue PNG using Pillow
        # No network calls; same bytes for same prompt (no random seed)
        img = Image.new("RGB", (1080, 1080), color=(30, 58, 95))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

class HuggingFaceImageProvider(ImageProvider):
    def __init__(self, token: str, model_id: str): ...
    async def generate(self, prompt: str) -> bytes:
        # Calls HF Inference API, raises ImageProviderError on failure/timeout/no-token
        ...
```

`ImageProviderError` is a custom exception in `image_providers.py`.

Factory function:

```python
def get_image_provider(settings: Settings) -> ImageProvider:
    if settings.image_provider == "huggingface":
        if not settings.hf_token:
            raise ImageProviderError("HF_TOKEN must be configured for HuggingFaceImageProvider")
        return HuggingFaceImageProvider(settings.hf_token, settings.hf_image_model)
    return MockImageProvider()
```

### `build_html` (`app/services/image_template.py`)

```python
ASPECT_RATIO_DIMS = {
    "1:1":  (1080, 1080),
    "4:5":  (1080, 1350),
    "16:9": (1920, 1080),
}

def build_html(visual_spec: VisualSpec, bg_bytes: bytes) -> str:
    """Build a self-contained HTML document for the infographic."""
    w, h = ASPECT_RATIO_DIMS[visual_spec.aspect_ratio]
    bg_b64 = base64.b64encode(bg_bytes).decode() if bg_bytes else ""
    key_points_li = "\n".join(f"<li>{p}</li>" for p in visual_spec.key_points)
    style_css = _get_style_css(visual_spec.style, w, h)
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>{style_css}</style>
</head>
<body>
  <div class="container">
    <div class="day-header">DAY {visual_spec.day_number:02d}</div>
    <h1 class="title">{visual_spec.title}</h1>
    <div class="visual-area">
      <img src="data:image/png;base64,{bg_b64}" alt="background" />
    </div>
    <ul class="key-points">{key_points_li}</ul>
    <div class="footer">#LearnWithAI</div>
  </div>
</body>
</html>"""
```

Style variants via `_get_style_css(style, w, h)`:

| `style` | Background | Text |
|---|---|---|
| `dark-tech` | `#0a0a1a` | `#e0e0ff` |
| `light-minimal` | `#ffffff` | `#1a1a1a` |
| `blue-gradient` | `linear-gradient(135deg, #1e3a5f, #4a90d9)` | `#ffffff` |

### `render_html_to_png` (`app/services/image_renderer.py`)

```python
from playwright.async_api import async_playwright
from pathlib import Path

async def render_html_to_png(
    html: str, output_path: Path, width: int, height: int
) -> Path:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.set_content(html, wait_until="networkidle")
        await page.screenshot(path=str(output_path), full_page=False)
        await browser.close()
    return output_path
```

Raises `RenderingError` (custom exception defined in `image_renderer.py`) if Playwright raises any exception.

### `generate_visual_spec` (`app/services/visual_spec_service.py`)

```python
async def generate_visual_spec(post: PostModel, topic: DayTopicModel) -> VisualSpec:
    """Call Qwen3 via Ollama to produce a VisualSpec from post + topic metadata."""
    prompt = _build_visual_spec_prompt(post, topic)
    raw = await _call_ollama(prompt)          # raises VisualSpecGenerationError on ConnectError
    cleaned = _strip_think_blocks(raw)        # strips <think>...</think>
    return _parse_visual_spec(cleaned)        # raises VisualSpecGenerationError on bad JSON
```

`VisualSpecGenerationError` is a custom exception defined in `visual_spec_service.py`. Ollama connectivity failures are caught and wrapped; other LLM response errors propagate without wrapping.

### `ImageRepository` (`app/services/image_repository.py`)

```python
class ImageRepository:
    def __init__(self, db: Session): ...

    def create(self, post_id: UUID, provider: str, prompt: str,
               visual_spec: dict) -> ImageModel: ...

    def update_status(self, image_id: UUID, status: str,
                      file_path: str | None = None,
                      width: int | None = None,
                      height: int | None = None,
                      visual_spec: dict | None = None) -> ImageModel: ...

    def get(self, image_id: UUID) -> ImageModel | None: ...

    def get_by_post(self, post_id: UUID) -> ImageModel | None: ...
```

### `run_pipeline` (`app/services/image_service.py`)

```python
async def run_pipeline(post_id: UUID, db: Session) -> ImageModel:
    """Orchestrate the full infographic generation pipeline for a post."""
    settings = get_settings()
    repo = ImageRepository(db)
    post = db.query(PostModel).options(joinedload(...)).filter(...).first()
    topic = post.day_topic

    # Step 2: create PENDING record
    image = repo.create(post_id=post_id, provider="", prompt="", visual_spec={})

    try:
        # Step 3: generate VisualSpec
        visual_spec = await generate_visual_spec(post, topic)

        # Step 4: mark GENERATING
        repo.update_status(image.id, ImageStatus.GENERATING)

        # Step 5: generate background image
        provider = get_image_provider(settings)
        bg_bytes = await provider.generate(visual_spec.visual_concept)

        # Step 6: build HTML
        html = build_html(visual_spec, bg_bytes)

        # Step 7: render PNG
        w, h = ASPECT_RATIO_DIMS[visual_spec.aspect_ratio]
        output_dir = Path(settings.image_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = int(datetime.now(timezone.utc).timestamp())
        output_path = output_dir / f"{post_id}_{ts}.png"
        await render_html_to_png(html, output_path, w, h)

        # Step 8: mark COMPLETED
        image = repo.update_status(
            image.id, ImageStatus.COMPLETED,
            file_path=str(output_path), width=w, height=h,
            visual_spec=visual_spec.model_dump(),
        )
        # also update provider and prompt on the record
        image.provider = type(provider).__name__
        image.prompt = visual_spec.visual_concept
        db.commit()
        db.refresh(image)

    except Exception:
        repo.update_status(image.id, ImageStatus.FAILED)
        db.refresh(image)

    return image
```

### `images` Router (`app/api/routes/images.py`)

```python
router = APIRouter(prefix="/api/images", tags=["images"])

@router.post("/generate/{post_id}", response_model=ImageResponse)
async def generate_image(post_id: UUID, db: Session = Depends(get_db)) -> ImageResponse:
    post = db.query(PostModel).filter(PostModel.id == post_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail=f"Post {post_id} not found.")
    image = await run_pipeline(post_id, db)
    return ImageResponse(
        success=(image.status == ImageStatus.COMPLETED),
        **ImageRead.model_validate(image).model_dump(),
    )
```

Registration in `app/main.py`:

```python
from app.api.routes.images import router as images_router
app.include_router(images_router)
```

---

## Data Models

### Entity-Relationship

```
ContentPlanModel ──< DayTopicModel ──< PostModel ──< ImageModel
                                                        │
                                                    (images table)
```

`ImageModel` is a child of `PostModel`. Deleting a post cascade-deletes all its images.

### `images` table DDL (Alembic migration `0003_add_images_table.py`)

```sql
CREATE TABLE images (
    id          UUID PRIMARY KEY,
    post_id     UUID NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    provider    VARCHAR(100) NOT NULL,
    prompt      TEXT NOT NULL,
    visual_spec JSON NOT NULL,
    file_path   VARCHAR(500),
    width       INTEGER,
    height      INTEGER,
    status      VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX ix_images_post_id ON images (post_id);
```

`down_revision = "0002"` — chained correctly after the posts migration.

### `VisualSpec` field constraints summary

| Field | Type | Constraint |
|---|---|---|
| `day_number` | int | ≥ 1 |
| `title` | str | min_length=1 |
| `subtitle` | str | no constraint |
| `visual_concept` | str | min_length=1 |
| `diagram_type` | Literal | one of 5 values |
| `diagram_nodes` | list[str] | 1–10 items |
| `key_points` | list[str] | 3–5 items |
| `style` | Literal | one of 3 values |
| `aspect_ratio` | Literal | one of 3 values |

### Settings additions (`app/core/config.py`)

```python
image_provider:  str = "mock"
hf_token:        str = ""
hf_image_model:  str = "stabilityai/stable-diffusion-xl-base-1.0"
image_output_dir: str = "images"
```

All loaded from environment variables (case-insensitive, same `SettingsConfigDict` as existing fields).

---

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: VisualSpec Round-Trip

*For any* valid `VisualSpec` object `v`, calling `VisualSpec.model_validate(v.model_dump())` SHALL produce a `VisualSpec` that is equal to `v` in all fields.

**Validates: Requirements 1.8**

This is a round-trip serialization property. Because `VisualSpec` uses `Literal` types, list constraints, and numeric bounds, any mis-handling of these constraints during (de)serialization would cause inequality. The Hypothesis generator must produce instances that satisfy all field constraints (valid `diagram_type`, `style`, `aspect_ratio` literals; `key_points` with 3–5 items; `diagram_nodes` with 1–10 items; `day_number ≥ 1`; non-empty `title` and `visual_concept`).

### Property 2: MockImageProvider Returns Valid PNG for Any Non-Empty Prompt

*For any* non-empty string `prompt`, `MockImageProvider().generate(prompt)` SHALL return `bytes` that start with the PNG magic bytes `b"\x89PNG\r\n\x1a\n"`, and calling `generate(prompt)` a second time with the same string SHALL return bytes with identical content.

**Validates: Requirements 2.2, 2.3**

This combines the validity and determinism requirements. The implementation uses `Pillow.Image.new()` with a fixed color and no random seed, so both sub-properties are satisfied by the same implementation. Varying prompts (including unicode, very long strings, single characters) exercises the "any non-empty prompt" quantifier without changing the expected result — only the coverage of the "non-empty" guard matters.

### Property 3: HTML Template Always Contains the Title

*For any* valid `VisualSpec` instance `v`, `build_html(v, b"")` SHALL return a non-empty string that contains `v.title` as a substring.

**Validates: Requirements 5.2, 5.9**

The title field drives the `<h1>` element in the template. For any combination of style, aspect ratio, day number, and key points, the title must appear verbatim in the rendered HTML. This property catches any template refactoring that accidentally drops or escapes the title. Using `b""` as the background bytes simplifies the generator while still exercising the full template path.

---

## Error Handling

### Custom Exceptions

| Exception | Module | Raised When |
|---|---|---|
| `VisualSpecGenerationError` | `visual_spec_service.py` | Ollama unreachable; JSON parse failure after stripping |
| `ImageProviderError` | `image_providers.py` | HF token missing; HF API non-2xx; HF API timeout |
| `RenderingError` | `image_renderer.py` | Playwright raises any exception during rendering |

### Pipeline Error Handling Strategy

All three custom exceptions (and any unexpected exceptions) are caught by the `try/except` in `run_pipeline`. The handler:

1. Calls `repo.update_status(image.id, ImageStatus.FAILED)` — records the failure in the database.
2. Returns the `ImageModel` (with `status="FAILED"`) rather than re-raising.
3. The router reads `image.status` to set `ImageResponse.success = False`.

This means the API always returns HTTP 200 (with `success=False`) for pipeline failures — the same pattern used for post generation in Phase 3. Only a missing `PostModel` (checked before pipeline entry) returns HTTP 404.

**No auto-retry** is implemented. If Qwen3 produces an invalid `VisualSpec`, the pipeline fails immediately and the user may re-trigger via the Regenerate Visual button.

### Connectivity Failures

- **Ollama unreachable**: `VisualSpecGenerationError` raised, caught by pipeline → `status=FAILED`.
- **HF API unreachable** (when `IMAGE_PROVIDER=huggingface`): `ImageProviderError` raised → `status=FAILED`.
- **Playwright browser missing**: `RenderingError` raised → `status=FAILED`.

### File System

`run_pipeline` calls `output_dir.mkdir(parents=True, exist_ok=True)` before writing, so missing directories are created silently. If the directory cannot be created (permissions), an `OSError` is raised and caught by the pipeline error handler → `status=FAILED`.

---

## Testing Strategy

### Test Infrastructure

- **Database**: SQLite in-memory (`sqlite://`) via the same `db_engine` / `db_session` / `client` fixture pattern as `test_posts.py`.
- **Image provider**: `MockImageProvider` everywhere in unit tests — no Hugging Face API calls.
- **Ollama**: `AsyncMock` patching `visual_spec_service.httpx.AsyncClient`, same pattern as Phase 3.
- **Playwright**: Marked `@pytest.mark.integration`; skipped automatically if playwright is not installed via `pytest.importorskip("playwright")`. Runs against a real headless Chromium.
- **PBT library**: [Hypothesis](https://hypothesis.readthedocs.io/) — already used in Phase 3.

### Unit Tests (`backend/tests/test_images.py`)

| Test | Requirement |
|---|---|
| Valid `VisualSpec` construction | 1.1, 1.2 |
| Invalid `VisualSpec`: too few `key_points` | 1.3 |
| Invalid `VisualSpec`: `day_number < 1` | 1.4 |
| Invalid `VisualSpec`: empty `title` | 1.6 |
| `MockImageProvider` returns PNG magic bytes | 2.2, 2.4 |
| HTML template contains DAY header, title, key points | 5.1, 5.2, 5.4 |
| `ImageModel` persistence round-trip (SQLite) | 3.1, 3.7 |
| Pipeline success → `status=COMPLETED` | 7.3 |
| Pipeline failure (provider raises) → `status=FAILED` | 7.4 |
| `POST /api/images/generate/{post_id}` happy path | 8.1, 8.3 |
| `POST /api/images/generate/{non_existent_id}` → 404 | 8.2 |

### Property-Based Tests (Hypothesis, `@given`)

| Property | Test Function | Settings |
|---|---|---|
| Property 1: VisualSpec round-trip | `test_visual_spec_round_trip` | `max_examples=100` |
| Property 2: MockImageProvider PNG + determinism | `test_mock_provider_returns_valid_png` | `max_examples=100` |
| Property 3: HTML template always contains title | `test_html_template_contains_title` | `max_examples=100` |

Each property test is tagged with a comment:

```python
# Feature: phase4-infographic-generation, Property 1: VisualSpec round-trip
```

### Integration Tests (Playwright, `@pytest.mark.integration`)

| Test | Requirement |
|---|---|
| Playwright renders 1080×1080 PNG for `aspect_ratio="1:1"` | 6.1, 6.2 |

Run with: `pytest backend/ -m integration`

Skip in CI without Playwright: `pytest backend/ -m "not integration"`

### Regression Guard

The existing 54 tests in Phases 1–3 (`test_content_plans.py`, `test_posts.py`, `test_health.py`) must continue passing after Phase 4 additions. Task 12 is an explicit checkpoint that runs `pytest backend/` before writing any new test code.

### Dual Testing Balance

Unit tests cover specific scenarios and edge cases. Property tests cover universal invariants across randomly generated inputs. Both are necessary:

- Unit tests catch concrete bugs (wrong field name, wrong status string).
- Property tests catch systematic issues (serialization drops a field for certain unicode inputs, template breaks for long titles).

Avoid writing unit tests for cases already covered by property generators — the `max_examples=100` setting on each property test already covers boundary values through shrinking.
