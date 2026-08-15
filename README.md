# LinkedIn AI Content Generator (Phase 1-4: Complete)

A local, privacy-friendly AI-powered system for generating structured LinkedIn
educational content series with **AI-generated infographics**. This repository implements:

- **Phase 1**: Foundation (health checks, database, Ollama connectivity)
- **Phase 2**: Multi-day content planning
- **Phase 3**: LinkedIn post generation
- **Phase 4**: Infographic generation ✅ **WORKING**

## Tech Stack

| Layer          | Technology            |
|----------------|------------------------|
| Frontend       | Streamlit              |
| Backend        | FastAPI + Uvicorn      |
| Database       | PostgreSQL (Docker)    |
| ORM            | SQLAlchemy 2.x + Alembic |
| Local LLM      | Ollama + Qwen2.5 3B    |
| Image Generation | Playwright + Chromium |

> Hardware target: Windows 11, Intel Core Ultra 5 225H, 16 GB RAM, Intel
> integrated graphics (no dedicated GPU). All local AI usage is CPU/RAM
> friendly — no GPU-dependent image generation is used.

## Project Structure

```
Post/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app entry point
│   │   ├── core/               # Config + logging
│   │   ├── db/                 # SQLAlchemy engine/session
│   │   ├── models/              # ORM models (future phases)
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── api/routes/          # API route handlers
│   │   └── services/            # Ollama service, etc.
│   └── tests/                   # Pytest tests
├── frontend/
│   └── app.py                    # Streamlit dashboard
├── scripts/                       # Utility scripts (future)
├── .env.example
├── docker-compose.yml             # PostgreSQL service
├── requirements.txt
└── README.md
```

## Prerequisites

- Python 3.11+ installed and available as `python` on PATH
- Docker Desktop installed and running (for PostgreSQL)
- [Ollama](https://ollama.com/download) installed for Windows

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

You should see `linkedin_ai_postgres` with status `healthy` (may take a few
seconds after starting).

### 5. Install and start Ollama

If not already installed, download and install Ollama for Windows from
https://ollama.com/download, then make sure the Ollama service is running
(it typically starts automatically and listens on `http://localhost:11434`).

To confirm it's running:

```bat
curl http://localhost:11434
```

### 6. Pull the Qwen2.5 3B model (recommended for 16 GB RAM)

```bat
ollama pull qwen2.5:3b
```

Verify it was pulled:

```bat
ollama list
```

**Note:** The .env file is configured to use `qwen2.5:3b` which is faster and more reliable on 16 GB RAM systems than `qwen3:4b`.

### 7. Install Playwright browsers (required for infographic generation)

```bat
playwright install chromium
```

This downloads the Chromium browser used for rendering infographics.

### 8. Start the FastAPI backend

From the project root (with the venv activated):

```bat
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Leave this terminal running.


### 9. Start the Streamlit frontend

Open a **new** terminal, activate the venv again, and run:

```bat
venv\Scripts\activate
streamlit run frontend/app.py
```

Streamlit will open in your browser (default: http://localhost:8501).

### 10. Test the health endpoint

In a new terminal:

```bat
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "ok"}
```

Check the aggregated system status (DB + Ollama):

```bat
curl http://localhost:8000/status
```

---

## Running Backend Tests

From the `backend/` directory (with venv activated):

```bat
cd backend
pytest
```

Expected result: **74 tests passed** (includes Phase 1-4 tests)

## Verifying Setup

Before starting the application, verify all dependencies are correctly installed:

```bat
python scripts\verify_setup.py
```

This checks:
- Python dependencies (FastAPI, Streamlit, Pillow, playwright, etc.)
- Playwright browsers (Chromium)
- Environment configuration (.env file)
- Output directory for images
- Ollama service connectivity

## Stopping Services

```bat
docker-compose down
```

Stop FastAPI and Streamlit with `Ctrl+C` in their respective terminals.

## API Endpoints (Phase 1-4)

| Method | Path      | Description                                    |
|--------|-----------|-------------------------------------------------|
| GET    | `/health` | Basic liveness check → `{"status": "ok"}`        |
| GET    | `/status` | Aggregated DB + Ollama connectivity status        |
| POST   | `/api/content-plans/generate` | Generate a multi-day content plan |
| GET    | `/api/content-plans/` | List all content plans |
| GET    | `/api/content-plans/{id}` | Get a specific plan |
| DELETE | `/api/content-plans/{id}` | Delete a content plan |
| POST   | `/api/posts/generate/{day_topic_id}` | Generate a LinkedIn post |
| POST   | `/api/posts/{id}/regenerate` | Regenerate an existing post |
| POST   | `/api/posts/{id}/approve` | Approve a post |
| PUT    | `/api/posts/{id}` | Update post content |
| POST   | `/api/images/generate/{post_id}` | Generate infographic for a post |

## Environment Variables

| Variable            | Default                                                        | Description                          |
|---------------------|-----------------------------------------------------------------|---------------------------------------|
| `DATABASE_URL`       | `postgresql+psycopg://postgres:postgres@localhost:5432/linkedin_ai` | SQLAlchemy database connection string |
| `OLLAMA_BASE_URL`    | `http://localhost:11434`                                        | Base URL of the local Ollama server   |
| `OLLAMA_MODEL`       | `qwen2.5:3b`                                                    | Model name used for local generation  |
| `OLLAMA_TIMEOUT_SECONDS` | `300`                                                       | Timeout for Ollama API calls (seconds) |
| `BACKEND_URL`        | `http://localhost:8000`                                         | Backend URL used by the Streamlit app |
| `IMAGE_PROVIDER`     | `mock`                                                          | Image provider ("mock" or "huggingface") |
| `IMAGE_OUTPUT_DIR`   | `images`                                                        | Directory for generated infographics  |

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
- AI-generated visual specifications
- HTML/CSS template rendering
- Playwright-based PNG generation
- Professional LinkedIn-style infographics
- Support for multiple aspect ratios (1:1, 4:5, 16:9)
- Local generation (no cloud APIs required)

## Troubleshooting

### Infographic Generation Issues

If infographic generation fails with timeout errors:

1. **Check Ollama model:** Ensure you're using `qwen2.5:3b` (not `qwen3:4b`)
   ```bash
   ollama list
   ```

2. **Increase timeout:** Edit `.env` and increase `OLLAMA_TIMEOUT_SECONDS`
   ```bash
   OLLAMA_TIMEOUT_SECONDS=600
   ```

3. **Verify Chromium:** Ensure Playwright browsers are installed
   ```bash
   playwright install chromium
   ```

4. **Check logs:** Backend terminal shows detailed error messages

See `INFOGRAPHIC_FIX_REPORT.md` for complete troubleshooting guide.

## Notes

- This is a **local-first** system. No LinkedIn browser automation or API
  publishing is implemented, by design, in this or future phases described
  here.
- Image generation will use CPU-friendly approaches (HTML/CSS → PNG), not
  GPU-dependent diffusion models.
