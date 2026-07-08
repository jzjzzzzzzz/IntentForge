"""Intent-level schema for a CAD request."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SupportedFamily = Literal["wall_mounted_bracket", "l_bracket"]


class IntentSpec(BaseModel):
    """Structured engineering intent extracted from a user request."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    family: SupportedFamily = Field(
        ...,
        description="Supported CAD model family.",
    )
    user_prompt: str = Field(
        ...,
        min_length=1,
        description="Original natural-language request.",
    )
    objective: str = Field(
        ...,
        min_length=1,
        description="Concise engineering objective for the model.",
    )
    requirements: list[str] = Field(
        default_factory=list,
        description="Structured requirements that should drive parameters and features.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit assumptions made during interpretation.",
    )
    unknowns: list[str] = Field(
        default_factory=list,
        description="Information that remains unresolved.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Intent metadata to carry into generated models and reports.",
    )
