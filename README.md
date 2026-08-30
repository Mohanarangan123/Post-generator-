# LinkedIn AI Content Generator (Phase 1-4: Complete)

A local, privacy-friendly AI-powered system for generating structured LinkedIn
educational content series with professional infographics. This repository implements:

- **Phase 1**: Foundation (health checks, database, Ollama connectivity)
- **Phase 2**: Multi-day content planning
- **Phase 3**: LinkedIn post generation
- **Phase 4**: Professional educational infographic generation (Cloudflare Workers AI)

## Tech Stack

| Layer          | Technology            |
|----------------|------------------------|
| Frontend       | Streamlit              |
| Backend        | FastAPI + Uvicorn      |
| Database       | PostgreSQL (Docker)    |
| ORM            | SQLAlchemy 2.x + Alembic |
| Local LLM      | Ollama + Qwen2.5 3B    |
| Image Gen      | Cloudflare Workers AI (Flux) |
| Text Rendering | Pillow (PIL)           |

> Hardware target: Windows 11, Intel Core Ultra 5 225H, 16 GB RAM, Intel
> integrated graphics. All local AI usage is CPU/RAM friendly — image generation uses Cloudflare's API (cloud-based, requires credentials).

## Project Structure

```
Post/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── core/               # Config + logging
│   │   ├── db/                 # SQLAlchemy engine/session
│   │   ├── models/              # ORM models (Phases 1-4)
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── api/routes/          # API route handlers
│   │   └── services/            # Ollama, Cloudflare, Pillow services
│   └── tests/                   # Pytest tests (all phases)
├── frontend/
│   └── app.py                    # Streamlit dashboard (Phases 1-4)
├── alembic/
│   └── versions/                 # Database migrations
├── images/                        # Reference infographic images (Phase 4)
├── outputs/
│   └── infographics/             # Generated infographic PNGs (Phase 4)
├── .env.example
├── docker-compose.yml             # PostgreSQL service
├── requirements.txt
└── README.md
```

## Prerequisites

- Python 3.11+ installed and available as `python` on PATH
- Docker Desktop installed and running (for PostgreSQL)
- [Ollama](https://ollama.com/download) installed for Windows
- **Phase 4 (Infographics):** Cloudflare account with Workers AI access

---

## Windows Setup — Exact Commands

Run these from the project root (`Post/`) in **PowerShell or cmd.exe**.

### 1. Create and activate a virtual environment

```bat
python -m venv venv
venv\Scripts\activate
```

### 2. Install Python dependencies

```bat
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure environment variables

```bat
copy .env.example .env
```

Edit `.env` if needed (defaults work for local development).

### 4. Start PostgreSQL (via Docker Compose)

```bat
docker-compose up -d
```

Verify the container is healthy:

```bat
docker ps
```

You should see `linkedin_ai_postgres` with status `healthy` (may take a few seconds).

### 5. Install and start Ollama

If not already installed, download and install Ollama for Windows from
https://ollama.com/download, then make sure the Ollama service is running.

Confirm it's running:

```bat
curl http://localhost:11434
```

### 6. Pull the Qwen2.5 3B model

```bat
ollama pull qwen2.5:3b
```

### 7. Start the FastAPI backend

From the project root (with venv activated):

```bat
cd backend
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Leave this terminal running.

### 8. Start the Streamlit frontend

Open a **new** terminal, activate the venv, and run:

```bat
venv\Scripts\activate
streamlit run frontend/app.py
```

Streamlit will open at http://localhost:8501.

### 9. Verify setup

Test the health endpoint:

```bat
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok"}
```

---

## Phase 4: Infographic Generation Setup

### Step 1: Create Cloudflare Account & Get Credentials

1. Go to [https://dash.cloudflare.com](https://dash.cloudflare.com) and sign up/log in
2. **Get Account ID:**
   - Go to **Account Settings** (bottom left)
   - Copy your **Account ID** (32-character hex string)

3. **Create API Token:**
   - Go to [https://dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens)
   - Click **Create Token**
   - Select **"Create Custom Token"**
   - Grant **Workers AI** or **AI Models: Run** permission
   - Set TTL to 365 days or longer
   - Create and copy the token

### Step 2: Add Credentials to .env

```bash
CLOUDFLARE_ACCOUNT_ID=your_account_id_here
CLOUDFLARE_API_TOKEN=your_api_token_here
```

### Step 3: Apply Database Migration

```bat
cd backend
alembic upgrade head
```

This adds the `infographic_generations` table (migration 0003).

### Step 4: Verify Credentials

```bat
python -c "from app.core.config import get_settings; s = get_settings(); print(f'Account: {s.cloudflare_account_id[:8]}...'); print(f'Token configured: {bool(s.cloudflare_api_token)}')"
```

### Free Tier Warning ⚠️

Cloudflare Workers AI provides a daily free neuron allocation. Usage beyond the free limit may require billing. Monitor your usage at [https://dash.cloudflare.com/](https://dash.cloudflare.com/).

---

## Running Tests

From the `backend/` directory (with venv activated):

```bat
cd backend
pytest
```

**Note:** Tests use mocked Cloudflare responses — no real API calls are made. The test suite validates:
- InfographicSpec and InfographicPanel validation
- Pillow text rendering (wrapping, layout, font fallback)
- Cloudflare provider error handling (401, 403, 429, timeout, invalid images)
- Database model creation and status transitions
- FastAPI endpoint validation
- All Phases 1-4 functionality

---

## API Endpoints

### Phases 1-3 Endpoints

| Method | Path                              | Description |
|--------|-----------------------------------|-------------|
| GET    | `/health`                         | Liveness check |
| GET    | `/status`                         | DB + Ollama status |
| POST   | `/api/content-plans/generate`     | Generate content plan |
| GET    | `/api/content-plans`              | List plans |
| DELETE | `/api/content-plans/{id}`         | Delete plan |
| POST   | `/api/posts/generate/{day_topic_id}` | Generate post |
| PUT    | `/api/posts/{id}`                 | Update post |

### Phase 4 Endpoints (Infographics)

| Method | Path                                      | Description |
|--------|-------------------------------------------|-------------|
| POST   | `/api/posts/{post_id}/infographic`        | Create infographic |
| GET    | `/api/infographics/{generation_id}`       | Get generation status |
| GET    | `/api/infographics/{generation_id}/image` | Download PNG |
| POST   | `/api/infographics/{generation_id}/retry` | Retry failed generation |

---

## Environment Variables

| Variable                           | Default                 | Description |
|------------------------------------|-------------------------|-------------|
| `DATABASE_URL`                     | `postgresql+psycopg://postgres:postgres@localhost:5432/linkedin_ai` | DB connection |
| `OLLAMA_BASE_URL`                  | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL`                     | `qwen2.5:3b`            | LLM model |
| `OLLAMA_TIMEOUT_SECONDS`           | `300`                   | Ollama timeout |
| `BACKEND_URL`                      | `http://localhost:8000` | Backend URL (frontend) |
| `CLOUDFLARE_ACCOUNT_ID`            | *(empty)*               | **Phase 4 required** |
| `CLOUDFLARE_API_TOKEN`             | *(empty)*               | **Phase 4 required** |
| `CLOUDFLARE_IMAGE_MODEL`           | `@cf/black-forest-labs/flux-2-klein-9b` | Flux model |
| `CLOUDFLARE_IMAGE_WIDTH`           | `1536`                  | Image width (16:9) |
| `CLOUDFLARE_IMAGE_HEIGHT`          | `864`                   | Image height (16:9) |
| `CLOUDFLARE_IMAGE_TIMEOUT_SECONDS` | `120`                   | Cloudflare timeout |
| `CLOUDFLARE_IMAGE_MAX_RETRIES`     | `2`                     | Retry attempts |
| `INFOGRAPHIC_OUTPUT_DIR`           | `outputs/infographics`  | PNG output directory |

---

## Features Implemented

### Phase 1: Foundation ✅
- FastAPI backend with health checks
- PostgreSQL database with SQLAlchemy ORM
- Alembic migrations
- Ollama integration
- Streamlit dashboard

### Phase 2: Content Planning ✅
- Multi-day content plan generation
- AI-powered topic progression
- Difficulty levels and categories
- Day-by-day learning objectives

### Phase 3: Post Generation ✅
- LinkedIn post generation per topic
- Edit and regenerate posts
- Approve posts for publishing
- Version tracking

### Phase 4: Infographic Generation ✅
- Cloudflare Workers AI (Flux) integration
- Professional educational infographic style (16:9, 1536×864)
- Pillow-based text rendering with:
  - Automatic word wrapping
  - Font size reduction
  - Multiple panel layouts (3 or 4)
  - High-contrast text colors
  - Font fallback system
- Reference image support
- Hybrid pipeline: Flux for illustrations + Pillow for exact text
- Database tracking of generation status
- Duplicate-click prevention
- Free quota protection with 429 handling
- Retry mechanism for failed generations
- Streamlit UI for generation and download

---

## Phase 4: Architecture & Design

### Why Hybrid Image + Text Rendering?

Image generation models (Flux) can produce spelling mistakes, especially with dense text. To ensure accuracy:

1. **Flux generates illustrated background** — No text rendered
2. **Pillow renders exact text afterward** — Guaranteed accuracy

This ensures text matches the original post content perfectly.

### Key Design Decisions

- **Cloudflare Flux model:** @cf/black-forest-labs/flux-2-klein-9b (cost-effective, fast)
- **No text in image prompt:** Flux explicitly told NOT to render letters, logos, watermarks
- **Atomic file writes:** Prevents incomplete images from being served
- **Provider abstraction:** Easy to swap Cloudflare for another provider later
- **Mocked tests:** No real Cloudflare API calls in test suite
- **Free quota protection:** Clear 429 handling, rate limiting, retry logic

### InfographicSpec Model

```python
class InfographicSpec(BaseModel):
    title: str  # max 90 chars
    subtitle: Optional[str]  # max 90 chars
    panels: list[InfographicPanel]  # 3 or 4 panels
    summary: str  # max 180 chars
    theme: str  # blue_navy, light_blue, professional_tech
    accent_color: str  # cyan, teal, white, navy

class InfographicPanel(BaseModel):
    number: int  # 1-4
    heading: str  # max 45 chars
    description: str  # max 180 chars
    visual_prompt: str  # Illustration prompt for Flux
    icon_hint: Optional[str]  # Optional visual hint
```

### Generation Pipeline

1. **Extract** post content → build InfographicSpec
2. **Load** reference images (up to 4, for style guidance)
3. **Call** Cloudflare Flux with detailed prompt
4. **Render** exact text onto image using Pillow
5. **Save** to `outputs/infographics/{post_id}_{generation_id}.png`
6. **Persist** to database with status/metadata

---

## Troubleshooting

### Ollama Issues

```bash
# Check if running
ollama list

# Check connectivity
curl http://localhost:11434
```

### Database Issues

```bash
# Ensure PostgreSQL container is running
docker-compose ps

# View logs
docker-compose logs
```

### Phase 4: Cloudflare Issues

| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Invalid token | Regenerate API token in Cloudflare dashboard |
| 403 Forbidden | Missing Workers AI permission | Update token with Workers AI scope |
| 429 Quota | Free allocation exhausted | Wait or enable billing in Cloudflare dashboard |
| Timeout | Model overloaded | Retry later; increase CLOUDFLARE_IMAGE_TIMEOUT_SECONDS |
| Invalid PNG | Corrupted response | Retry generation |

### Backend Logs

```bash
cd backend
uvicorn app.main:app --reload --log-level debug
```

---

## Stopping Services

```bat
docker-compose down
```

Stop FastAPI and Streamlit with `Ctrl+C`.

---

## Notes

- **Privacy:** All content processing is local (Ollama) or uses your own Cloudflare account
- **No automation:** LinkedIn publishing must be done manually
- **Phases independent:** Phases 1-3 work without Phase 4 (Cloudflare optional)
- **No secrets in repo:** Never commit `.env` with real credentials

---

## Files & Changes for Phase 4

### New Files Created
- `backend/app/models/infographic.py` — ORM model
- `backend/app/schemas/infographic.py` — Pydantic schemas
- `backend/app/services/cloudflare_provider.py` — Cloudflare integration
- `backend/app/services/infographic_renderer.py` — Pillow text rendering
- `backend/app/services/infographic_service.py` — Orchestration
- `backend/app/services/infographic_repository.py` — Database access
- `backend/app/api/routes/infographics.py` — FastAPI endpoints
- `backend/alembic/versions/0003_add_infographic_generation_table.py` — Database migration
- `backend/tests/test_infographics.py` — Comprehensive test suite

### Modified Files
- `backend/app/main.py` — Added infographics router
- `backend/app/core/config.py` — Added Cloudflare settings
- `backend/app/models/__init__.py` — Export infographic models
- `backend/requirements.txt` — Added Pillow
- `frontend/app.py` — Added Phase 4 tab
- `.env.example` — Added Cloudflare variables
- `README.md` — Updated with Phase 4 documentation

### Database Changes
- Alembic migration 0003: Creates `infographic_generations` table with columns:
  - `id`, `post_id`, `provider`, `model`, `status`, `width`, `height`, `prompt_hash`, `output_path`, `error_message`, `created_at`, `completed_at`
  - Indexes on `post_id` and `status`

---

## Testing Phase 4

```bash
cd backend
pytest tests/test_infographics.py -v
```

Expected: **All tests pass** (no real Cloudflare API calls)

---

## License & Attribution

- Generated with Cloudflare Workers AI
- Text content powered by Ollama (Qwen2.5)
- UI by Streamlit
- Infrastructure by FastAPI + PostgreSQL

---

## Support & Limits

- **Cloudflare Free Tier:** Check current daily allocation at https://dash.cloudflare.com/
- **Ollama Timeouts:** Increase `OLLAMA_TIMEOUT_SECONDS` for slower systems
- **Image Quality:** Varies by Cloudflare model; reference images improve consistency
- **Retry Logic:** Automatic retry on temporary errors (500, timeout); manual retry on permanent errors (401, 403)
