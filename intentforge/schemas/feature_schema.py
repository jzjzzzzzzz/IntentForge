"""Feature history plan schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SupportedFamily = Literal["wall_mounted_bracket"]


class FeatureStep(BaseModel):
    """One explainable CAD feature operation in construction order."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_:-]*$",
        description="Stable feature step identifier.",
    )
    operation: str = Field(
        ...,
        min_length=1,
        description="Generator operation to perform later.",
    )
    parameters: list[str] = Field(
        default_factory=list,
        description="Named parameters used by this feature.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Prior feature step IDs that this step depends on.",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Design reason for this feature.",
    )
    outputs: list[str] = Field(
        default_factory=list,
        description="Named solids, faces, workplanes, or tags produced by this step.",
    )
    validation_refs: list[str] = Field(
        default_factory=list,
        description="Validation check IDs related to this step.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeaturePlan(BaseModel):
    """Ordered feature history plan for one supported model family."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    family: SupportedFamily = Field(..., description="Supported CAD model family.")
    construction_strategy: str = Field(
        ...,
        min_length=1,
        description="High-level modeling strategy.",
    )
    steps: list[FeatureStep] = Field(
        ...,
        min_length=1,
        description="Ordered feature history.",
    )
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_steps(self) -> "FeaturePlan":
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"duplicate feature step id: {step.id}")
            missing_dependencies = [dependency for dependency in step.depends_on if dependency not in seen]
            if missing_dependencies:
                joined = ", ".join(missing_dependencies)
                raise ValueError(f"feature step {step.id} depends on unknown or later steps: {joined}")
            seen.add(step.id)
        return self
