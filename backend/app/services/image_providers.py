"""
Pluggable image provider interface.

ImageProvider (ABC)
├── MockImageProvider    — deterministic solid-color PNG, no network
└── HuggingFaceImageProvider — HF Inference API (cloud)
"""
import io
import logging
from abc import ABC, abstractmethod

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

HF_TIMEOUT_SECONDS = 60.0


class ImageProviderError(Exception):
    """Raised when an image provider fails to generate an image."""


class ImageProvider(ABC):
    """Abstract base class for all image providers."""

    @abstractmethod
    async def generate(self, prompt: str) -> bytes:
        """Generate a background image for the given prompt. Returns PNG bytes."""


class MockImageProvider(ImageProvider):
    """
    Deterministic mock provider — returns a solid-color PNG.
    No network calls; no random seed; same prompt → same bytes.
    """

    async def generate(self, prompt: str) -> bytes:
        if not prompt:
            raise ValueError("prompt must not be empty")
        img = Image.new("RGB", (1080, 1080), color=(30, 58, 95))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


class HuggingFaceImageProvider(ImageProvider):
    """
    Calls the Hugging Face Inference API to generate a background image.
    Requires HF_TOKEN and HF_IMAGE_MODEL to be configured.
    """

    def __init__(self, token: str, model_id: str) -> None:
        self._token = token
        self._model_id = model_id

    async def generate(self, prompt: str) -> bytes:
        if not self._token:
            raise ImageProviderError(
                "HF_TOKEN must be configured to use HuggingFaceImageProvider."
            )
        if not self._model_id:
            raise ImageProviderError(
                "HF_IMAGE_MODEL must be configured to use HuggingFaceImageProvider."
            )
        url = f"https://api-inference.huggingface.co/models/{self._model_id}"
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with httpx.AsyncClient(timeout=HF_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json={"inputs": prompt}, headers=headers)
        except httpx.TimeoutException as exc:
            raise ImageProviderError(
                f"Hugging Face Inference API request timed out after {HF_TIMEOUT_SECONDS}s."
            ) from exc
        if response.status_code >= 300:
            raise ImageProviderError(
                f"Hugging Face Inference API returned status {response.status_code}."
            )
        content_type = response.headers.get("content-type", "")
        if "image" not in content_type and not response.content.startswith(b"\x89PNG"):
            raise ImageProviderError(
                f"Hugging Face Inference API returned non-PNG content: {content_type}"
            )
        return response.content


def get_image_provider(settings) -> ImageProvider:
    """Factory: return the correct ImageProvider based on settings."""
    if settings.image_provider == "huggingface":
        if not settings.hf_token:
            raise ImageProviderError(
                "HF_TOKEN must be configured when IMAGE_PROVIDER=huggingface."
            )
        return HuggingFaceImageProvider(settings.hf_token, settings.hf_image_model)
    # Default: mock (covers "mock" and any unrecognized value)
    return MockImageProvider()
