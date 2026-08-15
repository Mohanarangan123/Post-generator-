"""
Service for generating VisualSpec from a PostModel via Qwen3/Ollama.
"""
import json
import logging
import re
from typing import Optional

import httpx

from app.core.config import get_settings
from app.schemas.image import VisualSpec

logger = logging.getLogger(__name__)


class VisualSpecGenerationError(Exception):
    """Raised when VisualSpec generation fails."""


def _build_visual_spec_prompt(post, topic) -> str:
    """Build the Ollama prompt for VisualSpec JSON generation."""
    parts = []
    if topic and getattr(topic, "day_number", None) is not None:
        parts.append(f"Day Number: {topic.day_number}")
    if topic and getattr(topic, "title", None):
        # Sanitize title: remove problematic characters
        title_clean = topic.title.encode('ascii', errors='replace').decode('ascii')
        title_clean = title_clean.replace('?', ' ')
        parts.append(f"Topic Title: {title_clean}")
    if topic and getattr(topic, "main_subject", None):
        subject_clean = topic.main_subject.encode('ascii', errors='replace').decode('ascii')
        subject_clean = subject_clean.replace('?', ' ')
        parts.append(f"Subject: {subject_clean}")
    if topic and getattr(topic, "category", None):
        parts.append(f"Category: {topic.category}")
    if topic and getattr(topic, "difficulty", None):
        parts.append(f"Difficulty: {topic.difficulty}")
    if post and getattr(post, "content", None):
        # Sanitize content: encode to ASCII, remove emoji and non-ASCII
        # Replace '?' from encode errors with space for readability
        content_sanitized = post.content.encode('ascii', errors='replace').decode('ascii')
        content_sanitized = content_sanitized.replace('?', ' ')
        # Remove multiple spaces
        content_sanitized = ' '.join(content_sanitized.split())
        parts.append(f"Post Content:\n{content_sanitized[:1000]}")

    context = "\n".join(parts)

    return f"""You are a visual designer creating infographic specifications for LinkedIn educational posts.

Given the following post information:
{context}

Generate a VisualSpec JSON object for this LinkedIn educational infographic.

STRICT OUTPUT RULES:
- Return ONLY a valid JSON object. No markdown, no code fences, no commentary, no <think> tags.
- The object must have exactly these keys:
  "day_number" (integer, same as the day number above or 1 if unknown),
  "title" (string, concise topic title, max 10 words),
  "subtitle" (string, brief subtitle or empty string),
  "visual_concept" (string, vivid description of the background image to generate),
  "diagram_type" (string, one of: "flowchart", "hierarchy", "comparison", "timeline", "list"),
  "diagram_nodes" (array of 3-7 strings, key concept labels),
  "key_points" (array of exactly 3-5 strings, each a short memorable insight),
  "style" (string, one of: "dark-tech", "light-minimal", "blue-gradient"),
  "aspect_ratio" (string, one of: "1:1", "4:5", "16:9")

Return the JSON object now:"""


def _strip_think_blocks(raw: str) -> str:
    """Remove <think>...</think> blocks and markdown fences from Ollama output."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).replace("```", "").strip()
    return cleaned


async def _call_ollama(prompt: str) -> str:
    """POST to Ollama /api/generate. Returns the response text."""
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    timeout_seconds = settings.ollama_timeout_seconds
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            logger.info(f"Calling Ollama at {url} (timeout: {timeout_seconds}s)")
            response = await client.post(url, json=payload)
            response.raise_for_status()
        return response.json().get("response", "")
    except httpx.ConnectError as exc:
        raise VisualSpecGenerationError(
            f"Ollama is unreachable at {settings.ollama_base_url}: {exc}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise VisualSpecGenerationError(
            f"Ollama request timed out after {timeout_seconds}s. "
            f"The model '{settings.ollama_model}' may be slow on this system. "
            f"Try increasing OLLAMA_TIMEOUT_SECONDS in .env or use a smaller model like qwen2.5:3b."
        ) from exc


def _parse_visual_spec(text: str) -> VisualSpec:
    """Parse a VisualSpec from cleaned JSON text."""
    # Try to extract JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VisualSpecGenerationError(
            f"LLM response could not be parsed as JSON: {exc}. "
            f"Raw (first 300 chars): {text[:300]!r}"
        ) from exc
    try:
        return VisualSpec(**data)
    except Exception as exc:
        raise VisualSpecGenerationError(
            f"LLM JSON does not match VisualSpec schema: {exc}"
        ) from exc


async def generate_visual_spec(post, topic) -> VisualSpec:
    """
    Generate a VisualSpec for the given post and topic using Qwen3.

    Raises:
        VisualSpecGenerationError: if Ollama is unreachable or response is invalid.
    """
    prompt = _build_visual_spec_prompt(post, topic)
    raw = await _call_ollama(prompt)
    cleaned = _strip_think_blocks(raw)
    return _parse_visual_spec(cleaned)
