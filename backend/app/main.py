"""
FastAPI application entry point.

Phase 1 scope:
- Application bootstrap (logging, CORS)
- /health endpoint (liveness)
- /status endpoint (DB + Ollama connectivity)

Content generation, models, and scheduling are intentionally NOT
implemented yet - they belong to later phases.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.content_plans import router as content_plans_router
from app.api.routes.health import router as health_router
from app.api.routes.posts import router as posts_router
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: log startup/shutdown events."""
    logger.info("Starting %s (environment=%s)", settings.app_name, settings.environment)
    logger.info("Configured Ollama model: %s @ %s", settings.ollama_model, settings.ollama_base_url)
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Local AI-powered LinkedIn content generation system (Phase 1: foundation, Phase 2: content planner).",
    version="0.1.0",
    lifespan=lifespan,
)

# Allow the Streamlit frontend (and local dev tools) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(content_plans_router)
app.include_router(posts_router)