"""
Pydantic schemas for Phase 4: Infographic Generation.

InfographicPanel represents a single content panel in the infographic.
InfographicSpec represents the complete infographic specification.
InfographicGenerationResponse represents the API response for generation status.
"""
import re
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class InfographicPanel(BaseModel):
    """A single panel in an infographic."""

    number: int = Field(..., ge=1, le=4, description="Panel number (1-4)")
    heading: str = Field(
        ...,
        max_length=45,
        description="Panel heading (max 45 chars)",
    )
    description: str = Field(
        ...,
        max_length=180,
        description="Panel description (max 180 chars)",
    )
    visual_prompt: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="Illustration prompt for Flux (no text rendering)",
    )
    icon_hint: Optional[str] = Field(
        None,
        max_length=50,
        description="Optional icon or visual hint",
    )

    @field_validator("heading", "description", mode="before")
    @classmethod
    def remove_markdown_and_whitespace(cls, v: str) -> str:
        """Remove markdown symbols and normalize whitespace."""
        if not isinstance(v, str):
            return v
        # Remove markdown symbols
        v = re.sub(r"[*#\-_`\[\](){}]", " ", v)
        # Normalize whitespace
        v = " ".join(v.split())
        return v.strip()

    @field_validator("heading", "description")
    @classmethod
    def strip_and_check_not_blank(cls, v: str) -> str:
        """Ensure value is not blank after processing."""
        if not isinstance(v, str):
            return v
        if not v.strip():
            raise ValueError("Value must not be blank or whitespace-only.")
        return v

    @field_validator("visual_prompt")
    @classmethod
    def clean_visual_prompt(cls, v: str) -> str:
        """Remove markdown symbols and unsupported control characters."""
        if not isinstance(v, str):
            return v
        v = re.sub(r"[#`\[\]{}]", " ", v)
        v = " ".join(v.split())
        return v.strip()


class InfographicSpec(BaseModel):
    """Complete specification for an infographic."""

    title: str = Field(
        ...,
        max_length=90,
        description="Infographic title (max 90 chars)",
    )
    subtitle: Optional[str] = Field(
        None,
        max_length=90,
        description="Optional subtitle (max 90 chars)",
    )
    panels: list[InfographicPanel] = Field(
        ...,
        min_items=3,
        max_items=4,
        description="3 or 4 content panels",
    )
    summary: str = Field(
        ...,
        max_length=180,
        description="Summary/conclusion text (max 180 chars)",
    )
    theme: str = Field(
        default="blue_navy",
        description="Visual theme: blue_navy, light_blue, professional_tech",
    )
    accent_color: str = Field(
        default="cyan",
        description="Accent color: cyan, teal, white, navy",
    )

    @field_validator("title", "subtitle", "summary", mode="before")
    @classmethod
    def remove_markdown_and_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Remove markdown symbols and normalize whitespace."""
        if v is None or not isinstance(v, str):
            return v
        # Remove markdown symbols
        v = re.sub(r"[*#\-_`\[\](){}]", " ", v)
        # Normalize whitespace
        v = " ".join(v.split())
        return v.strip()

    @field_validator("title", "summary")
    @classmethod
    def strip_and_check_not_blank(cls, v: str) -> str:
        """Ensure required fields are not blank."""
        if not isinstance(v, str):
            return v
        if not v.strip():
            raise ValueError("Value must not be blank or whitespace-only.")
        return v

    @field_validator("panels")
    @classmethod
    def check_panel_numbers(cls, v: list[InfographicPanel]) -> list[InfographicPanel]:
        """Ensure panel numbers are sequential."""
        if not v:
            return v
        numbers = [p.number for p in v]
        if numbers != sorted(set(numbers)):
            raise ValueError("Panel numbers must be sequential (1, 2, 3) or (1, 2, 3, 4)")
        return v

    model_config = {"from_attributes": True}


class InfographicGenerationRead(BaseModel):
    """Read schema for infographic generation status."""

    id: UUID
    post_id: UUID
    provider: str
    model: str
    status: str
    width: int
    height: int
    prompt_hash: str
    output_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str  # ISO format datetime
    completed_at: Optional[str] = None  # ISO format datetime

    model_config = {"from_attributes": True}


class InfographicGenerationResponse(BaseModel):
    """API response for infographic generation."""

    success: bool
    message: str
    generation: Optional[InfographicGenerationRead] = None
    image_url: Optional[str] = None


class InfographicRetryRequest(BaseModel):
    """Request to retry a failed infographic generation."""

    regenerate_image: bool = Field(
        default=False,
        description="If true, regenerate image; if false, recompose text only",
    )
