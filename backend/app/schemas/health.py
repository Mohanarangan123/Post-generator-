"""
Pydantic schemas for health and status endpoints.
"""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response schema for the basic /health endpoint."""
    status: str = "ok"


class ComponentStatus(BaseModel):
    """Status of a single dependent component (DB, Ollama, etc.)."""
    connected: bool
    message: str


class OllamaStatus(ComponentStatus):
    """Status of the Ollama service, including the configured model."""
    model: str
    model_available: bool | None = None


class SystemStatusResponse(BaseModel):
    """Aggregated status response for the /status endpoint."""
    status: str
    database: ComponentStatus
    ollama: OllamaStatus
