"""
Health and system status endpoints.

- GET /health  -> simple liveness check for the API itself
- GET /status  -> aggregated status of dependent services (DB, Ollama)
"""
import logging

from fastapi import APIRouter

from app.db.session import check_db_connection
from app.schemas.health import (
    ComponentStatus,
    HealthResponse,
    OllamaStatus,
    SystemStatusResponse,
)
from app.services.ollama_service import check_ollama_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Basic liveness endpoint. Always returns ok if the API is running."""
    return HealthResponse(status="ok")


@router.get("/status", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    """
    Aggregated status of the backend and its dependencies:
    database connectivity and Ollama (local LLM) connectivity.
    """
    db_connected, db_message = check_db_connection()
    ollama_result = check_ollama_connection()

    overall_status = "ok" if db_connected and ollama_result["connected"] else "degraded"

    return SystemStatusResponse(
        status=overall_status,
        database=ComponentStatus(connected=db_connected, message=db_message),
        ollama=OllamaStatus(
            connected=ollama_result["connected"],
            message=ollama_result["message"],
            model=ollama_result["model"],
            model_available=ollama_result["model_available"],
        ),
    )
