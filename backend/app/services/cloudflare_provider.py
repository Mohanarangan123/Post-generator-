"""
Cloudflare Workers AI provider for image generation.

Implements async HTTP client integration with Cloudflare's REST API
for the Flux image generation model.

Handles:
- Authenticated requests with Bearer token
- Timeout and retry logic
- Proper error handling (401, 403, 429, etc.)
- Binary image validation
- Request ID logging
"""
import base64
import asyncio
import hashlib
import logging
from typing import Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CloudflareImageGenerationError(Exception):
    """Base exception for Cloudflare image generation errors."""

    pass


class CloudflareAuthError(CloudflareImageGenerationError):
    """Raised when authentication/authorization fails (401, 403)."""

    pass


class CloudflareQuotaError(CloudflareImageGenerationError):
    """Raised when quota is exceeded (429)."""

    pass


class CloudflareTimeoutError(CloudflareImageGenerationError):
    """Raised when request times out."""

    pass


class CloudflareInvalidImageError(CloudflareImageGenerationError):
    """Raised when returned data is not a valid image."""

    pass


class CloudflareWorkersAIProvider:
    """
    Async provider for Cloudflare Workers AI image generation.

    Uses httpx for async HTTP client with proper timeout and retry handling.
    """

    def __init__(self):
        """Initialize provider with settings."""
        self.settings = get_settings()
        self.account_id = self.settings.cloudflare_account_id
        self.api_token = self.settings.cloudflare_api_token
        self.model = self.settings.cloudflare_image_model
        self.width = self.settings.cloudflare_image_width
        self.height = self.settings.cloudflare_image_height
        self.timeout = self.settings.cloudflare_image_timeout_seconds
        self.max_retries = self.settings.cloudflare_image_max_retries

        self.base_url = "https://api.cloudflare.com/client/v4"
        self.endpoint = (
            f"{self.base_url}/accounts/{self.account_id}/ai/run/{self.model}"
        )

    def _validate_credentials(self) -> None:
        """Validate that required credentials are set."""
        if not self.account_id or not self.account_id.strip():
            raise CloudflareAuthError(
                "CLOUDFLARE_ACCOUNT_ID is not set. "
                "Get it from: https://dash.cloudflare.com/profile/api-tokens"
            )
        if not self.api_token or not self.api_token.strip():
            raise CloudflareAuthError(
                "CLOUDFLARE_API_TOKEN is not set. "
                "Create a token with Workers AI permission at: https://dash.cloudflare.com/profile/api-tokens"
            )

    def _get_headers(self) -> dict[str, str]:
        """Return HTTP headers with authentication."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def _validate_image_bytes(self, image_bytes: bytes) -> None:
        """Validate that image_bytes represent a real image (PNG or JPEG)."""
        if len(image_bytes) < 4:
            raise CloudflareInvalidImageError(
                f"Image too small ({len(image_bytes)} bytes)"
            )

        # PNG magic number: 0x89504E47
        png_magic = b"\x89PNG\r\n\x1a\n"
        # JPEG magic number: 0xFFD8
        jpeg_magic = b"\xFF\xD8"
        
        if image_bytes.startswith(png_magic):
            return  # Valid PNG
        
        if image_bytes.startswith(jpeg_magic):
            return  # Valid JPEG
        
        raise CloudflareInvalidImageError(
            "Returned data is not a valid PNG or JPEG image (invalid magic bytes)"
        )

    async def _call_with_retry(
        self,
        prompt: str,
        reference_images: Optional[list[bytes]] = None,
    ) -> bytes:
        """
        Call Cloudflare Flux API with retry logic.

        Args:
            prompt: Text prompt for image generation
            reference_images: Optional list of reference image bytes

        Returns:
            Binary image data (PNG)

        Raises:
            CloudflareAuthError: 401/403 or missing credentials
            CloudflareQuotaError: 429 quota exhausted
            CloudflareTimeoutError: Request timeout
            CloudflareInvalidImageError: Invalid response data
            CloudflareImageGenerationError: Other errors
        """
        self._validate_credentials()

        async with httpx.AsyncClient() as client:
            for attempt in range(self.max_retries + 1):
                try:
                    logger.info(
                        "Cloudflare Flux request (attempt %d/%d): %s",
                        attempt + 1,
                        self.max_retries + 1,
                        self.endpoint,
                    )

                    # Cloudflare Flux API requires multipart/form-data encoding
                    # Build multipart form data
                    form_data = {
                        "prompt": (None, prompt),
                        "height": (None, str(self.height)),
                        "width": (None, str(self.width)),
                    }
                    
                    # Add reference images if provided (up to 4)
                    if reference_images:
                        reference_images = reference_images[:4]
                        for i, img_bytes in enumerate(reference_images):
                            form_data[f"image_reference_{i}"] = (
                                f"ref_{i}.png",
                                img_bytes,
                                "image/png"
                            )
                    
                    response = await client.post(
                        self.endpoint,
                        files=form_data,
                        headers={"Authorization": self._get_headers()["Authorization"]},
                        timeout=self.timeout,
                    )

                    # Check for authentication errors (permanent)
                    if response.status_code == 401:
                        logger.error("Cloudflare authentication failed (401)")
                        raise CloudflareAuthError(
                            "Unauthorized: Invalid or missing API token. "
                            "Check CLOUDFLARE_API_TOKEN."
                        )

                    if response.status_code == 403:
                        logger.error("Cloudflare permission denied (403)")
                        raise CloudflareAuthError(
                            "Forbidden: API token does not have Workers AI permission. "
                            "Create a new token at: https://dash.cloudflare.com/profile/api-tokens"
                        )

                    # Check for quota errors (can retry after delay)
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After", "60")
                        try:
                            retry_after_secs = float(retry_after)
                        except ValueError:
                            retry_after_secs = 60.0

                        if attempt < self.max_retries:
                            logger.warning(
                                "Quota exhausted (429). Retrying after %s seconds...",
                                retry_after_secs,
                            )
                            await asyncio.sleep(retry_after_secs)
                            continue

                        logger.error(
                            "Quota exhausted (429) after %d retries", self.max_retries
                        )
                        raise CloudflareQuotaError(
                            f"Free quota exhausted. "
                            f"Cloudflare Workers AI may require billing for additional generations. "
                            f"Retry after {retry_after_secs} seconds."
                        )

                    # Check for other HTTP errors
                    if response.status_code >= 400:
                        error_msg = f"HTTP {response.status_code}"
                        try:
                            error_data = response.json()
                            if "errors" in error_data:
                                error_msg = str(error_data["errors"])
                        except Exception:  # noqa: BLE001
                            pass

                        if attempt < self.max_retries and response.status_code >= 500:
                            logger.warning(
                                "Server error (%d). Retrying...", response.status_code
                            )
                            await asyncio.sleep(2 ** attempt)  # exponential backoff
                            continue

                        logger.error(
                            "Cloudflare API error (%d): %s", response.status_code, error_msg
                        )
                        raise CloudflareImageGenerationError(
                            f"Cloudflare API error: {error_msg}"
                        )

                    # Success: 200 OK
                    if response.status_code == 200:
                        content_type = str(response.headers.get("content-type", "")).lower()

                        # Depending on the model/API version, Cloudflare may return
                        # JSON containing base64 or the image bytes directly.
                        if "application/json" in content_type:
                            response_data = response.json()
                            logger.debug("Cloudflare response: %s", str(response_data)[:200])
                            
                            # Extract image from response
                            if "result" in response_data and "image" in response_data["result"]:
                                image_b64 = response_data["result"]["image"]
                                image_bytes = base64.b64decode(image_b64)
                            elif "image" in response_data:
                                image_b64 = response_data["image"]
                                image_bytes = base64.b64decode(image_b64)
                            else:
                                logger.error("No image field in Cloudflare response: %s", response_data)
                                raise CloudflareImageGenerationError(
                                    f"Invalid response format: missing image field. Got: {response_data}"
                                )
                            
                            # Validate image bytes
                            await self._validate_image_bytes(image_bytes)
                            logger.info(
                                "Cloudflare Flux image generated successfully (%d bytes)",
                                len(image_bytes),
                            )
                            return image_bytes

                        image_bytes = response.content
                        logger.debug("Binary image response length: %d", len(image_bytes))
                        await self._validate_image_bytes(image_bytes)
                        logger.info(
                            "Cloudflare Flux image generated successfully (%d bytes)",
                            len(image_bytes),
                        )
                        return image_bytes

                    logger.error(
                        "Unexpected Cloudflare response (%d)", response.status_code
                    )
                    raise CloudflareImageGenerationError(
                        f"Unexpected response status: {response.status_code}"
                    )

                except httpx.TimeoutException as exc:
                    if attempt < self.max_retries:
                        logger.warning(
                            "Request timeout. Retrying (attempt %d/%d)...",
                            attempt + 1,
                            self.max_retries + 1,
                        )
                        await asyncio.sleep(2 ** attempt)
                        continue

                    logger.error("Request timeout after %d retries", self.max_retries)
                    raise CloudflareTimeoutError(
                        f"Cloudflare request timed out after {self.timeout} seconds. "
                        f"The model may be busy or your network is slow. Try again later."
                    ) from exc

                except (CloudflareAuthError, CloudflareQuotaError):
                    # Permanent errors: don't retry
                    raise

                except httpx.HTTPError as exc:
                    if attempt < self.max_retries:
                        logger.warning(
                            "HTTP error: %s. Retrying (attempt %d/%d)...",
                            exc,
                            attempt + 1,
                            self.max_retries + 1,
                        )
                        await asyncio.sleep(2 ** attempt)
                        continue

                    logger.error("HTTP error after %d retries: %s", self.max_retries, exc)
                    raise CloudflareImageGenerationError(
                        f"HTTP error: {exc}"
                    ) from exc

        # Should not reach here
        raise CloudflareImageGenerationError(
            "Failed to generate image after all retries"
        )

    async def generate_image(
        self,
        prompt: str,
        reference_images: Optional[list[bytes]] = None,
    ) -> bytes:
        """
        Generate an image using Cloudflare Flux.

        Args:
            prompt: Text prompt for image generation (no letters, words, logos, watermarks)
            reference_images: Optional list of reference image bytes (max 4)

        Returns:
            Binary PNG image data

        Raises:
            CloudflareAuthError: Authentication/permission errors
            CloudflareQuotaError: Free quota exhausted
            CloudflareTimeoutError: Request timeout
            CloudflareInvalidImageError: Invalid response data
            CloudflareImageGenerationError: Other generation errors
        """
        logger.debug("Generating image with prompt length: %d", len(prompt))
        return await self._call_with_retry(prompt, reference_images)

    @staticmethod
    def hash_prompt(prompt: str) -> str:
        """
        Hash a prompt for deduplication.

        Args:
            prompt: The prompt text

        Returns:
            SHA256 hash (hex string)
        """
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
