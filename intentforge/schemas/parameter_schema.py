"""Named parameter table schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SupportedFamily = Literal["wall_mounted_bracket"]
ParameterSource = Literal["user", "assumed", "derived", "default"]
ParameterValue = int | float | str | bool


class Parameter(BaseModel):
    """A named, editable parameter with provenance and design rationale."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    name: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Stable machine-readable parameter name.",
    )
    value: ParameterValue = Field(
        ...,
        description="Current parameter value.",
    )
    unit: str | None = Field(
        default=None,
        description="Engineering unit, if applicable.",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Human-readable meaning of the parameter.",
    )
    source: ParameterSource = Field(
        default="user",
        description="Where the parameter value came from.",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Why this parameter exists in the model.",
    )
    locked: bool = Field(
        default=False,
        description="Whether edit-intent handling should preserve this value unless explicit.",
    )
    min_value: float | None = Field(
        default=None,
        description="Optional inclusive lower bound for numeric values.",
    )
    max_value: float | None = Field(
        default=None,
        description="Optional inclusive upper bound for numeric values.",
    )
    expression: str | None = Field(
        default=None,
        description="Optional expression for derived parameters.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_numeric_bounds(self) -> "Parameter":
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise ValueError("min_value cannot be greater than max_value")

        is_numeric = isinstance(self.value, int | float) and not isinstance(self.value, bool)
        if is_numeric and self.min_value is not None and self.value < self.min_value:
            raise ValueError(f"{self.name} is below min_value")
        if is_numeric and self.max_value is not None and self.value > self.max_value:
            raise ValueError(f"{self.name} is above max_value")

        if self.expression and self.source != "derived":
            raise ValueError("parameters with expression must use source='derived'")

        return self


class ParameterTable(BaseModel):
    """A complete named parameter table for one model family."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    family: SupportedFamily = Field(..., description="Supported CAD model family.")
    parameters: list[Parameter] = Field(
        default_factory=list,
        description="Named model parameters.",
    )
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_names(self) -> "ParameterTable":
        names = [parameter.name for parameter in self.parameters]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            joined = ", ".join(duplicates)
            raise ValueError(f"duplicate parameter names: {joined}")
        return self

    def by_name(self) -> dict[str, Parameter]:
        """Return parameters keyed by stable name."""

        return {parameter.name: parameter for parameter in self.parameters}

    def get(self, name: str) -> Parameter:
        """Return one parameter by name or raise KeyError."""

        parameters = self.by_name()
        if name not in parameters:
            raise KeyError(name)
        return parameters[name]
