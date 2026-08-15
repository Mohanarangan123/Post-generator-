"""
Curriculum generation service.

Orchestrates prompt construction, Ollama LLM call (non-streaming),
JSON parsing/repair, and validation to produce a structured day-by-day
LinkedIn learning plan.
"""
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.content_plan import DayTopic

logger = logging.getLogger(__name__)

OLLAMA_TIMEOUT_SECONDS = 120.0


def _build_prompt(
    main_subject: str,
    number_of_days: int,
    audience: str,
    difficulty: str,
) -> str:
    """Build the structured prompt for the Ollama LLM."""
    return f"""You are a LinkedIn learning curriculum designer.

Generate a {number_of_days}-day learning plan about "{main_subject}" for "{audience}" at {difficulty} level.

STRICT OUTPUT RULES:
- Return ONLY a valid JSON array. No markdown, no code fences, no commentary, no <think> tags.
- The array must contain exactly {number_of_days} objects.
- Each object must have these exact keys:
  "day_number" (integer, 1 to {number_of_days}),
  "main_subject" (string, the overall subject: "{main_subject}"),
  "title" (string, concise unique topic title, max 10 words),
  "short_description" (string, 1-2 sentences explaining the topic),
  "difficulty" (string, one of: Beginner / Intermediate / Advanced),
  "category" (string, thematic grouping such as "Fundamentals", "Architecture", "Applications"),
  "learning_objective" (string, real-world measurable outcome starting with an action verb)

CURRICULUM RULES:
- Day 1 MUST start with absolute fundamentals/prerequisites.
- Progress logically from fundamentals toward advanced concepts day by day.
- Every title must be unique. No duplicate or near-duplicate titles allowed.
- Every day_number must be unique and exactly sequential from 1 to {number_of_days}.
- All topics must be directly relevant to "{main_subject}". No loosely related or off-topic entries.
- Learning objectives must be practical and achievable in one day of study.
- Titles must be concise (max 10 words).
- Do NOT include LinkedIn post formatting, hashtags, or emojis.
- Do NOT hallucinate technologies or tools that do not exist.

Return the JSON array now:"""


async def _call_ollama(prompt: str) -> str:
    """POST to Ollama /api/generate (non-streaming). Returns the response text."""
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    logger.debug("Calling Ollama at %s with model %s", url, settings.ollama_model)
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
    data = response.json()
    raw_text = data.get("response", "")
    logger.debug("Ollama raw response (first 200 chars): %s", raw_text[:200])
    return raw_text


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    """
    Extract the first valid JSON array from a raw LLM text response.

    Strategy:
    1. Strip <think>...</think> blocks (Qwen3 thinking mode).
    2. Strip markdown code fences.
    3. Attempt direct json.loads.
    4. Extract first [...] substring and attempt json.loads.
    5. Raise descriptive ValueError if still unparseable.
    """
    # 1. Strip <think> blocks
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # 2. Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned).replace("```", "").strip()

    # 3. Direct parse
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 4. Extract first [...] substring
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(cleaned[start : end + 1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    raise ValueError(
        f"LLM response could not be parsed as a JSON array. "
        f"Raw response (first 500 chars): {raw[:500]!r}"
    )


def _validate_topics(topics: list[DayTopic], expected_count: int) -> None:
    """
    Validate that topics have sequential unique day numbers and unique titles.

    Raises:
        ValueError: with a descriptive message identifying the violation.
    """
    day_numbers = [t.day_number for t in topics]
    expected_sequence = list(range(1, expected_count + 1))

    if sorted(day_numbers) != expected_sequence:
        raise ValueError(
            f"Day numbers are not sequential 1..{expected_count}. "
            f"Got (sorted): {sorted(day_numbers)}"
        )

    titles_lower = [t.title.strip().lower() for t in topics]
    seen: set[str] = set()
    duplicates: list[str] = []
    for title in titles_lower:
        if title in seen:
            duplicates.append(title)
        seen.add(title)

    if duplicates:
        raise ValueError(
            f"Duplicate topic titles detected: {duplicates}"
        )


async def generate_curriculum(
    main_subject: str,
    number_of_days: int,
    audience: str,
    difficulty: str,
) -> list[DayTopic]:
    """
    Generate a day-by-day learning curriculum using Ollama.

    Returns:
        Validated list of DayTopic objects.

    Raises:
        httpx.ConnectError: if Ollama server is unreachable.
        httpx.TimeoutException: if the request times out.
        httpx.HTTPStatusError: if Ollama returns a non-2xx response.
        ValueError: if the response cannot be parsed or fails validation.
    """
    prompt = _build_prompt(main_subject, number_of_days, audience, difficulty)
    raw = await _call_ollama(prompt)
    raw_list = _parse_json_array(raw)

    try:
        topics = [DayTopic(**item) for item in raw_list]
    except Exception as exc:
        raise ValueError(
            f"LLM returned JSON that does not match the DayTopic schema: {exc}. "
            f"First item: {raw_list[0] if raw_list else 'empty list'}"
        ) from exc

    _validate_topics(topics, number_of_days)
    logger.info(
        "Generated curriculum for '%s': %d days", main_subject, len(topics)
    )
    return topics
