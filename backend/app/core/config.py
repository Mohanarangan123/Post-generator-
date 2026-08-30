"""
Application configuration.

Loads settings from environment variables (and a local .env file if present)
using pydantic-settings. Centralizing configuration here means the rest of
the codebase never reads os.environ directly.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to this file's location so it works regardless of
# which directory uvicorn / pytest is launched from.
# This file is at:  backend/app/core/config.py
# The .env file is at: <project_root>/.env  (three levels up)
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Application settings sourced from environment variables."""

    # --- General ---
    app_name: str = "LinkedIn AI Content Generator"
    environment: str = "development"
    log_level: str = "INFO"

    # --- Database ---
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/linkedin_ai"

    # --- Ollama / Local LLM ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    ollama_timeout_seconds: float = 300.0  # Timeout for Ollama API calls

    # --- Frontend / CORS ---
    backend_url: str = "http://localhost:8000"

    # --- Cloudflare Workers AI (Phase 4: Infographic Generation) ---
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_image_model: str = "@cf/black-forest-labs/flux-2-klein-9b"
    cloudflare_image_width: int = 1536
    cloudflare_image_height: int = 864
    cloudflare_image_timeout_seconds: float = 120.0
    cloudflare_image_max_retries: int = 2
    infographic_output_dir: str = "outputs/infographics"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (loaded once per process)."""
    return Settings()
