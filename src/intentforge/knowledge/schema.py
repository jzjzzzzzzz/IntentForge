"""Schemas for IntentForge engineering knowledge rules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


RuleSeverity = Literal["info", "recommendation", "warning", "error"]


class DesignKnowledgeRule(BaseModel):
    """Human engineering knowledge represented as a deterministic rule."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    applies_to: list[str] = Field(..., min_length=1)
    condition: dict[str, Any] = Field(default_factory=dict)
    severity: RuleSeverity
    recommendation: str = Field(..., min_length=1)
    source_reference: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("applies_to")
    @classmethod
    def validate_applies_to(cls, value: list[str]) -> list[str]:
        allowed = {"wall_mounted_bracket", "l_bracket"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unsupported applies_to family: {', '.join(unknown)}")
        return value

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, value: dict[str, Any]) -> dict[str, Any]:
        expression = value.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError("condition.expression is required")
        return value


class KnowledgeFinding(BaseModel):
    """Result of applying one engineering knowledge rule."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    rule_id: str
    rule_name: str
    category: str
    severity: RuleSeverity
    passed: bool
    message: str
    recommendation: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompiledConstraint(BaseModel):
    """Machine-readable constraint compiled from a knowledge rule."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    rule_id: str
    expression: str
    source: str = "engineering_rule"
    confidence: float = Field(..., ge=0.0, le=1.0)
