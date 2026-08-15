<<<<<<< HEAD
# LinkedIn AI Content Generator (Phase 1: Foundation)

A local, privacy-friendly AI-powered system for generating structured LinkedIn
educational content series. This repository currently implements **Phase 1
only**: the foundational project skeleton, health checks, and connectivity
verification for the database and local LLM. Content generation, scheduling,
and image generation are **not yet implemented**.

## Tech Stack (Phase 1)

| Layer          | Technology            |
|----------------|------------------------|
| Frontend       | Streamlit              |
| Backend        | FastAPI + Uvicorn      |
| Database       | PostgreSQL (Docker)    |
| ORM            | SQLAlchemy 2.x + Alembic |
| Local LLM      | Ollama + Qwen3 4B      |

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

### 6. Pull the Qwen3 4B model

```bat
ollama pull qwen3:4b
```

Verify it was pulled:

```bat
ollama list
```

### 7. Start the FastAPI backend

From the project root (with the venv activated):

```bat
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Leave this terminal running.


### 8. Start the Streamlit frontend

Open a **new** terminal, activate the venv again, and run:

```bat
venv\Scripts\activate
streamlit run frontend/app.py
```

Streamlit will open in your browser (default: http://localhost:8501).

### 9. Test the health endpoint

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

These tests only check the `/health` endpoint and do not require Docker or
Ollama to be running.

## Stopping Services

```bat
docker-compose down
```

Stop FastAPI and Streamlit with `Ctrl+C` in their respective terminals.

## API Endpoints (Phase 1)

| Method | Path      | Description                                    |
|--------|-----------|-------------------------------------------------|
| GET    | `/health` | Basic liveness check → `{"status": "ok"}`        |
| GET    | `/status` | Aggregated DB + Ollama connectivity status        |

## Environment Variables

| Variable            | Default                                                        | Description                          |
|---------------------|-----------------------------------------------------------------|---------------------------------------|
| `DATABASE_URL`       | `postgresql+psycopg://postgres:postgres@localhost:5432/linkedin_ai` | SQLAlchemy database connection string |

| `OLLAMA_BASE_URL`    | `http://localhost:11434`                                        | Base URL of the local Ollama server   |
| `OLLAMA_MODEL`       | `qwen3:4b`                                                       | Model name used for local generation  |
| `BACKEND_URL`        | `http://localhost:8000`                                         | Backend URL used by the Streamlit app |

## Roadmap (Not Yet Implemented)

- Phase 2: Multi-day content series generation using Qwen3 4B via Ollama
- Phase 3: LinkedIn post drafting per day
- Phase 4: HTML/CSS → PNG infographic generation
- Phase 5: BGE-M3 embeddings + vector search
- Phase 6: Review workflow + status tracking
- Phase 7: LinkedIn native scheduler integration (manual scheduling assist only —
  no browser automation or API auto-publishing)

## Notes

- This is a **local-first** system. No LinkedIn browser automation or API
  publishing is implemented, by design, in this or future phases described
  here.
- Image generation will use CPU-friendly approaches (HTML/CSS → PNG), not
  GPU-dependent diffusion models.
=======
# Post-generator-
>>>>>>> 5ae00ae21b439cb23ea03bfcd1ff3bf7fa84b152
