"""Edit-intent request and report schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from intentforge.schemas.validation_schema import ValidationReport

SupportedFamily = Literal["wall_mounted_bracket", "l_bracket"]
EditValue = int | float | str | bool


class EditRequest(BaseModel):
    """A later modification request that should preserve design intent."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    family: SupportedFamily = Field(..., description="Supported CAD model family.")
    target_model_id: str | None = Field(
        default=None,
        description="Existing generated model identifier, if available.",
    )
    change_request: str = Field(
        default="",
        description="Natural-language edit request.",
    )
    parameter_updates: dict[str, EditValue] = Field(
        default_factory=dict,
        description="Direct named parameter updates requested by the user.",
    )
    add_requirements: list[str] = Field(default_factory=list)
    remove_requirements: list[str] = Field(default_factory=list)
    preserve_intent: list[str] = Field(
        default_factory=list,
        description="Intent statements that should remain true after the edit.",
    )
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_has_edit(self) -> "EditRequest":
        if not (
            self.change_request.strip()
            or self.parameter_updates
            or self.add_requirements
            or self.remove_requirements
        ):
            raise ValueError("edit request must include a change")
        return self


class EditReport(BaseModel):
    """Result of applying or evaluating an edit-intent request."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    family: SupportedFamily = Field(..., description="Supported CAD model family.")
    target_model_id: str | None = None
    accepted: bool = Field(..., description="Whether the edit can be applied.")
    changes_applied: list[str] = Field(default_factory=list)
    rejected_changes: list[str] = Field(default_factory=list)
    updated_parameters: dict[str, EditValue] = Field(default_factory=dict)
    changed_parameters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Parameter changes with old value, new value, and reason.",
    )
    preserved_parameters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Parameters or intent constraints preserved by the edit.",
    )
    rejected_edits: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rejected requested edits with reasons.",
    )
    failed_constraints: list[str] = Field(
        default_factory=list,
        description="Constraint failures that prevented acceptance.",
    )
    validation_summary: str = Field(
        default="",
        description="Summary from geometry validation after applying an accepted edit.",
    )
    human_readable_explanation: str = Field(
        default="",
        description="Plain-language explanation of the edit decision.",
    )
    warnings: list[str] = Field(default_factory=list)
    validation_report: ValidationReport | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
