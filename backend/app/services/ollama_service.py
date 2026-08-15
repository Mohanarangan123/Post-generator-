"""
Service for checking the availability of the local Ollama LLM server.

This does NOT perform any content generation in Phase 1 - it only verifies
that the Ollama server is reachable and (optionally) that the configured
model has been pulled locally.
"""
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Keep requests fast so the /status endpoint never hangs the UI.
REQUEST_TIMEOUT_SECONDS = 3.0


def check_ollama_connection() -> dict:
    """
    Check whether the Ollama server is reachable and whether the configured
    model is available locally.

    Returns:
        dict with keys: connected (bool), message (str), model (str),
        model_available (bool | None)
    """
    settings = get_settings()
    base_url = settings.ollama_base_url.rstrip("/")
    model = settings.ollama_model

    result = {
        "connected": False,
        "message": "Ollama server unreachable",
        "model": model,
        "model_available": None,
    }

    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()

        result["connected"] = True
        result["message"] = "Ollama server reachable"

        available_models = [m.get("name", "") for m in data.get("models", [])]
        # Ollama model names may or may not include the ":tag" suffix; compare loosely.
        model_available = any(
            m == model or m.split(":")[0] == model.split(":")[0]
            for m in available_models
        )
        result["model_available"] = model_available

        if not model_available:
            result["message"] = (
                f"Ollama reachable, but model '{model}' not found locally. "
                f"Run: ollama pull {model}"
            )

    except httpx.ConnectError as exc:
        logger.warning("Ollama connection failed: %s", exc)
        result["message"] = (
            "Could not connect to Ollama. Is it installed and running? "
            f"(expected at {base_url})"
        )
    except httpx.HTTPStatusError as exc:
        logger.warning("Ollama returned an error status: %s", exc)
        result["message"] = f"Ollama returned an error: {exc.response.status_code}"
    except Exception as exc:  # noqa: BLE001 - report any unexpected failure
        logger.error("Unexpected error checking Ollama: %s", exc)
        result["message"] = f"Unexpected error checking Ollama: {exc}"

    return result
