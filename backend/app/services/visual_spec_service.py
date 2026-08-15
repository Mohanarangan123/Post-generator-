"""
Service for generating VisualSpec from a PostModel via Qwen3/Ollama.
"""
import json
import logging
import re

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
        title_clean = topic.title.encode("ascii", errors="replace").decode("ascii")
        title_clean = title_clean.replace("?", " ")
        parts.append(f"Topic Title: {title_clean}")
    if topic and getattr(topic, "main_subject", None):
        subject_clean = topic.main_subject.encode("ascii", errors="replace").decode("ascii")
        subject_clean = subject_clean.replace("?", " ")
        parts.append(f"Subject: {subject_clean}")
    if topic and getattr(topic, "category", None):
        parts.append(f"Category: {topic.category}")
    if topic and getattr(topic, "difficulty", None):
        parts.append(f"Difficulty: {topic.difficulty}")
    if post and getattr(post, "content", None):
        content_sanitized = post.content.encode("ascii", errors="replace").decode("ascii")
        content_sanitized = content_sanitized.replace("?", " ")
        content_sanitized = " ".join(content_sanitized.split())
        parts.append(f"Post Content:\n{content_sanitized[:1200]}")

    context = "\n".join(parts)

    return f"""You are a visual designer creating infographic specifications for a professional LinkedIn educational post.

Given the following post information:
{context}

Generate a VisualSpec JSON object for this infographic.

STRICT OUTPUT RULES:
- Return ONLY valid JSON. No markdown fences, no extra commentary, no <think> tags.
- Use one of these diagram_type values: "process", "flowchart", "comparison", "lifecycle", "architecture", "steps", "concept", "hierarchy", "timeline", "list".
- Use semantic fields that describe the infographic itself: title, subtitle, day, category, layout_type, nodes, checklist, illustration_prompt, connections, icons.
- If you use legacy names, keep them compatible with the schema, but prefer semantic keys.
- nodes must be an array of objects with this shape: {{"step": 1, "title": "Install Python", "description": "Download and install Python"}}.
- checklist must be an array of 3-5 brief, memorable insights.
- illustration_prompt must describe only decorative/illustrative artwork, never final infographic text.
- Do not include any text inside the illustration itself.
- The generated JSON must match these semantic fields:
  {{
    "title": string,
    "subtitle": string,
    "day": integer,
    "category": string,
    "layout_type": string,
    "nodes": [{{"step": integer, "title": string, "description": string}}],
    "checklist": [string, string, string],
    "illustration_prompt": string,
    "connections": [{{"from": integer, "to": integer, "type": "arrow"}}],
    "icons": [string],
    "style": "dark-tech" | "light-minimal" | "blue-gradient",
    "aspect_ratio": "1:1" | "4:5" | "16:9"
  }}

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
            logger.info("Calling Ollama at %s (timeout: %s)", url, timeout_seconds)
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

    if "diagram_nodes" in data and data["diagram_nodes"] and isinstance(data["diagram_nodes"][0], str):
        data["diagram_nodes"] = [
            {"step": idx + 1, "title": node, "description": ""}
            for idx, node in enumerate(data["diagram_nodes"])
        ]

    try:
        return VisualSpec(**data)
    except Exception as exc:
        raise VisualSpecGenerationError(
            f"LLM JSON does not match VisualSpec schema: {exc}"
        ) from exc


async def generate_visual_spec(post, topic) -> VisualSpec:
    """Generate a VisualSpec for the given post and topic using Qwen3."""
    prompt = _build_visual_spec_prompt(post, topic)
    raw = await _call_ollama(prompt)
    cleaned = _strip_think_blocks(raw)
    return _parse_visual_spec(cleaned)
