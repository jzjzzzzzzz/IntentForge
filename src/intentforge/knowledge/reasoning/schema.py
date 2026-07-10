"""Stable schemas for deterministic engineering reasoning reports."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


REASONING_ENGINE_VERSION = "1.0"

ReasoningStepType = Literal[
    "observation",
    "implication",
    "tradeoff",
    "conflict",
    "recommendation",
    "priority",
    "limitation",
]

RuleInteractionType = Literal[
    "reinforces",
    "conflicts",
    "depends_on",
    "affects",
    "duplicates",
    "mitigates",
]

ReasoningConflictType = Literal[
    "parameter_conflict",
    "recommendation_conflict",
    "priority_conflict",
    "geometry_constraint_conflict",
]

RecommendationPriority = Literal[
    "critical",
    "high",
    "medium",
    "low",
    "informational",
]

ALLOWED_STEP_TYPES = (
    "observation",
    "implication",
    "tradeoff",
    "conflict",
    "recommendation",
    "priority",
    "limitation",
)

ALLOWED_INTERACTION_TYPES = (
    "reinforces",
    "conflicts",
    "depends_on",
    "affects",
    "duplicates",
    "mitigates",
)

ALLOWED_CONFLICT_TYPES = (
    "parameter_conflict",
    "recommendation_conflict",
    "priority_conflict",
    "geometry_constraint_conflict",
)

ALLOWED_PRIORITIES = (
    "critical",
    "high",
    "medium",
    "low",
    "informational",
)

PRIORITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
}


def canonical_json(data: Any) -> str:
    """Serialize JSON-compatible data deterministically."""

    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(prefix: str, data: Any, length: int = 12) -> str:
    """Build a deterministic short ID from canonical JSON data."""

    digest = hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


class ReasoningStep(BaseModel):
    """One traceable step in an engineering reasoning chain."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    step_id: str
    step_type: ReasoningStepType
    rule_ids: list[str] = Field(default_factory=list)
    statement: str = Field(..., min_length=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)
    sequence: int = Field(..., ge=0)


class RuleInteraction(BaseModel):
    """Relationship between two or more knowledge rules."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    interaction_id: str
    rule_ids: list[str] = Field(..., min_length=1)
    interaction_type: RuleInteractionType
    description: str = Field(..., min_length=1)
    effect: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineeringTradeoff(BaseModel):
    """Advisory benefit/cost statement tied to knowledge rules."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tradeoff_id: str
    source_rule_ids: list[str] = Field(..., min_length=1)
    benefit: str = Field(..., min_length=1)
    cost: str = Field(..., min_length=1)
    affected_parameters: list[str] = Field(default_factory=list)
    severity: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    recommendation: str = Field(..., min_length=1)


class ReasoningConflict(BaseModel):
    """A deterministic advisory conflict between rule recommendations."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    conflict_id: str
    rule_ids: list[str] = Field(..., min_length=2)
    description: str = Field(..., min_length=1)
    conflict_type: ReasoningConflictType
    resolution_strategy: str = Field(..., min_length=1)
    severity: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)


class PrioritizedRecommendation(BaseModel):
    """Ranked engineering recommendation produced by the reasoning engine."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    recommendation_id: str
    rule_ids: list[str] = Field(..., min_length=1)
    priority: RecommendationPriority
    action: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    expected_effect: str = Field(..., min_length=1)
    affected_parameters: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)


class EngineeringReasoningReport(BaseModel):
    """Serializable deterministic engineering reasoning report."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    report_id: str
    timestamp: str
    model_family: str
    reasoning_version: str = REASONING_ENGINE_VERSION
    source_knowledge_report_id: str
    observations: list[ReasoningStep] = Field(default_factory=list)
    interactions: list[RuleInteraction] = Field(default_factory=list)
    tradeoffs: list[EngineeringTradeoff] = Field(default_factory=list)
    conflicts: list[ReasoningConflict] = Field(default_factory=list)
    recommendations: list[PrioritizedRecommendation] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def reasoning_report_identity_payload(report_data: dict[str, Any]) -> dict[str, Any]:
    """Return the deterministic report identity payload.

    Timestamps and output paths are intentionally excluded so the same rules,
    findings, metrics, and reasoning version produce the same report ID.
    """

    return {
        "model_family": report_data.get("model_family"),
        "reasoning_version": report_data.get("reasoning_version"),
        "source_knowledge_report_id": report_data.get("source_knowledge_report_id"),
        "observations": report_data.get("observations", []),
        "interactions": report_data.get("interactions", []),
        "tradeoffs": report_data.get("tradeoffs", []),
        "conflicts": report_data.get("conflicts", []),
        "recommendations": report_data.get("recommendations", []),
        "summary": report_data.get("summary", {}),
        "limitations": report_data.get("limitations", []),
    }


def make_reasoning_report_id(report_data: dict[str, Any]) -> str:
    """Build a deterministic engineering reasoning report ID."""

    return stable_digest("reasoning", reasoning_report_identity_payload(report_data))
