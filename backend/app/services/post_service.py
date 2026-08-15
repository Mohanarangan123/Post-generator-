import logging
import re
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

POST_TIMEOUT_SECONDS = 120.0
DEFAULT_RETRIES = 3


def _build_post_prompt(topic) -> str:
    return f"""You are a LinkedIn content writer creating educational posts.

Write a LinkedIn post for DAY {topic.day_number}: {topic.title}

Topic details:
- Subject: {topic.main_subject}
- Category: {topic.category}
- Difficulty: {topic.difficulty}
- Description: {topic.short_description}
- Learning objective: {topic.learning_objective}

STRICT FORMAT RULES — follow this structure exactly:
DAY {topic.day_number}: {topic.title}

[A one-sentence hook that grabs attention]

\u2705 A simple explanation:
[Explain the concept in plain language, 2-3 sentences]

\u2705 A real-world example:
[One concrete, specific real-world example, 2-3 sentences]

\u2705 How it works:
[Step-by-step or mechanistic explanation, 3-4 sentences]

\u2705 Why it matters:
[Business or practical relevance, 2-3 sentences]

\U0001f4a1 Key takeaway:
[One short memorable sentence]

[One engaging question for the reader]

[3 to 5 relevant hashtags, e.g. #Python #MachineLearning]

CONTENT RULES:
- Professional but accessible English — no jargon without explanation
- Short paragraphs for mobile readability
- Use ONLY the \u2705 and \U0001f4a1 symbols shown above — no other emojis
- Do NOT include fake statistics or unsupported claims
- Do NOT add markdown formatting, code fences, or commentary outside the post
- Return ONLY the post text, nothing else"""


def _clean_response(raw: str) -> str:
    """Remove <think>...</think> blocks and markdown code fences from Ollama output."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```(?:\w+)?\s*", "", cleaned).replace("```", "").strip()
    return cleaned


async def generate_post_content(
    topic,
    retries: int = DEFAULT_RETRIES,
    timeout_seconds: float = POST_TIMEOUT_SECONDS,
) -> str:
    """
    Generate LinkedIn post content for a DayTopic using Ollama.

    Returns:
        Cleaned post text string.

    Raises:
        Exception: After all retries are exhausted.
        ValueError: If the cleaned response is empty.
    """
    settings = get_settings()
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    prompt = _build_post_prompt(topic)
    last_exc: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(
                    url,
                    json={
                        "model": settings.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                    },
                )
                response.raise_for_status()
            raw = response.json().get("response", "")
            cleaned = _clean_response(raw)
            if not cleaned:
                raise ValueError("Ollama returned an empty post response.")
            logger.info(
                "Generated post for day %d on attempt %d", topic.day_number, attempt
            )
            return cleaned
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.HTTPStatusError,
            ValueError,
        ) as exc:
            last_exc = exc
            logger.warning(
                "Post generation attempt %d/%d failed for day %d: %s",
                attempt,
                retries,
                topic.day_number,
                exc,
            )

    raise last_exc  # exhausted all retries
