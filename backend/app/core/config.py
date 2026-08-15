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

    # --- Image generation ---
    image_provider: str = "mock"  # "mock" or "huggingface"
    hf_token: str = ""  # Hugging Face API token
    hf_image_model: str = "black-forest-labs/FLUX.1-dev"  # preferred HF model
    image_output_dir: str = "images"  # output directory for PNGs

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
