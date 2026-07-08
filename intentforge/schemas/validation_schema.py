"""Validation report schemas for generated CAD models."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

SupportedFamily = Literal["wall_mounted_bracket", "l_bracket"]
ValidationStatus = Literal["pass", "fail", "warning", "not_run"]
ValidationSeverity = Literal["info", "warning", "error"]
MeasuredValue = int | float | str | bool | None


class ValidationCheck(BaseModel):
    """One validation check result tied to intent, parameters, or features."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_:-]*$",
        description="Stable validation check identifier.",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="What the check verifies.",
    )
    status: ValidationStatus = Field(..., description="Result status.")
    severity: ValidationSeverity = Field(default="error")
    measured_value: MeasuredValue = Field(default=None)
    expected_value: MeasuredValue = Field(default=None)
    tolerance: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None)
    related_parameters: list[str] = Field(default_factory=list)
    related_features: list[str] = Field(default_factory=list)
    message: str = Field(default="")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @computed_field
    @property
    def name(self) -> str:
        """User-facing check name."""

        return self.id

    @computed_field
    @property
    def expected(self) -> MeasuredValue:
        """User-facing expected value."""

        return self.expected_value

    @computed_field
    @property
    def actual(self) -> MeasuredValue:
        """User-facing actual value."""

        return self.measured_value

    @computed_field
    @property
    def passed(self) -> bool:
        """Return True when the check did not fail."""

        return self.status in {"pass", "warning"}

    @computed_field
    @property
    def explanation(self) -> str:
        """User-facing explanation for the result."""

        return self.message or self.description


class ValidationReport(BaseModel):
    """Validation results for a generated or planned model."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    family: SupportedFamily = Field(..., description="Supported CAD model family.")
    model_id: str | None = Field(
        default=None,
        description="Identifier for the generated model, if one exists.",
    )
    checks: list[ValidationCheck] = Field(default_factory=list)
    summary: str = Field(default="")
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_check_ids(self) -> "ValidationReport":
        check_ids = [check.id for check in self.checks]
        duplicates = sorted({check_id for check_id in check_ids if check_ids.count(check_id) > 1})
        if duplicates:
            joined = ", ".join(duplicates)
            raise ValueError(f"duplicate validation check ids: {joined}")
        return self

    @property
    def passed(self) -> bool:
        """Return True only when no check failed or remains unrun."""

        return all(check.status in {"pass", "warning"} for check in self.checks)

    @computed_field
    @property
    def valid(self) -> bool:
        """User-facing report validity."""

        return self.passed

    @computed_field
    @property
    def warnings(self) -> list[str]:
        """Warning messages from non-failing checks."""

        return [
            check.message or check.description
            for check in self.checks
            if check.status == "warning" or check.severity == "warning"
        ]

    @computed_field
    @property
    def failed_checks(self) -> list[ValidationCheck]:
        """Return checks with failing status."""

        return [check for check in self.checks if check.status == "fail"]
