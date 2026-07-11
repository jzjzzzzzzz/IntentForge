"""Typed schemas for structural review-decision differential audits."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from intentforge.assurance.schema import canonical_digest


REVIEW_DIFF_SCHEMA_VERSION = "1.0"

DeltaCategory = Literal[
    "subject",
    "policy",
    "evaluation_graph",
    "finding",
    "condition",
    "outcome",
    "capability",
    "evidence",
    "rule",
    "limitation",
    "provenance",
]
DeltaChangeType = Literal["added", "removed", "modified"]
DecisionTransition = Literal[
    "unchanged",
    "acceptance_elevated",
    "acceptance_constrained",
    "status_changed",
]
ComplianceImpact = Literal[
    "none",
    "more_permissive",
    "more_restrictive",
    "structural_change",
]


class SemanticDecisionDelta(BaseModel):
    """One keyed structural change; rendered prose is not authoritative."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    delta_id: str = ""
    category: DeltaCategory
    entity_key: str = Field(..., min_length=1)
    change_type: DeltaChangeType
    before: Any = None
    after: Any = None
    changed_fields: list[str] = Field(default_factory=list)
    compliance_impact: ComplianceImpact = "structural_change"
    security_relevant: bool = False
    summary_code: str = Field(..., min_length=1)
    content_id: str = ""

    @model_validator(mode="after")
    def validate_identity(self) -> "SemanticDecisionDelta":
        expected_content = canonical_digest("review_semantic_delta_content", self.deterministic_payload())
        expected_id = canonical_digest(
            "review_semantic_delta",
            {"category": self.category, "entity_key": self.entity_key, "content_id": expected_content},
        )
        if self.content_id and self.content_id != expected_content:
            raise ValueError(f"semantic delta content ID mismatch: {self.entity_key}")
        if self.delta_id and self.delta_id != expected_id:
            raise ValueError(f"semantic delta ID mismatch: {self.entity_key}")
        if not self.content_id:
            object.__setattr__(self, "content_id", expected_content)
        if not self.delta_id:
            object.__setattr__(self, "delta_id", expected_id)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data.pop("delta_id", None)
        data.pop("content_id", None)
        data["changed_fields"] = sorted(data["changed_fields"])
        return data


class ReviewDecisionDiff(BaseModel):
    """Deterministic structural comparison of two review decisions."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    diff_id: str = ""
    schema_version: str = REVIEW_DIFF_SCHEMA_VERSION
    baseline_decision_id: str
    baseline_content_id: str
    candidate_decision_id: str
    candidate_content_id: str
    identical: bool
    decision_transition: DecisionTransition
    baseline_status: str
    candidate_status: str
    policy_changed: bool
    evaluation_graph_changed: bool
    deltas: list[SemanticDecisionDelta] = Field(default_factory=list)
    added_check_ids: list[str] = Field(default_factory=list)
    removed_check_ids: list[str] = Field(default_factory=list)
    modified_check_ids: list[str] = Field(default_factory=list)
    added_condition_check_ids: list[str] = Field(default_factory=list)
    removed_condition_check_ids: list[str] = Field(default_factory=list)
    modified_condition_check_ids: list[str] = Field(default_factory=list)
    security_compliance_delta_ids: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    content_id: str = ""
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identity_and_order(self) -> "ReviewDecisionDiff":
        ordered = sorted(self.deltas, key=lambda item: (item.category, item.entity_key, item.delta_id))
        if len({item.delta_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate semantic delta IDs")
        if self.deltas != ordered:
            object.__setattr__(self, "deltas", ordered)
        security_ids = sorted(item.delta_id for item in ordered if item.security_relevant)
        if self.security_compliance_delta_ids and self.security_compliance_delta_ids != security_ids:
            raise ValueError("security/compliance delta index mismatch")
        if not self.security_compliance_delta_ids:
            object.__setattr__(self, "security_compliance_delta_ids", security_ids)
        expected_content = canonical_digest("review_decision_diff_content", self.deterministic_payload())
        expected_id = canonical_digest("review_decision_diff", {"content_id": expected_content})
        if self.content_id and self.content_id != expected_content:
            raise ValueError("review decision diff content ID mismatch")
        if self.diff_id and self.diff_id != expected_id:
            raise ValueError("review decision diff ID mismatch")
        if not self.content_id:
            object.__setattr__(self, "content_id", expected_content)
        if not self.diff_id:
            object.__setattr__(self, "diff_id", expected_id)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        for field_name in ("diff_id", "content_id", "runtime_metadata"):
            data.pop(field_name, None)
        data["deltas"] = sorted(
            data["deltas"], key=lambda item: (item["category"], item["entity_key"], item["delta_id"])
        )
        for field_name in (
            "added_check_ids",
            "removed_check_ids",
            "modified_check_ids",
            "added_condition_check_ids",
            "removed_condition_check_ids",
            "modified_condition_check_ids",
            "security_compliance_delta_ids",
        ):
            data[field_name] = sorted(data[field_name])
        return data

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


class MultiVariantReviewDiff(BaseModel):
    """One baseline compared with one or more deterministic decision variants."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    audit_id: str = ""
    schema_version: str = REVIEW_DIFF_SCHEMA_VERSION
    baseline_decision_id: str
    variant_decision_ids: list[str] = Field(..., min_length=1)
    pairwise_diffs: list[ReviewDecisionDiff] = Field(..., min_length=1)
    outcome_matrix: dict[str, str]
    policy_matrix: dict[str, dict[str, str]]
    identical_variant_count: int = Field(ge=0)
    elevated_variant_count: int = Field(ge=0)
    constrained_variant_count: int = Field(ge=0)
    changed_variant_count: int = Field(ge=0)
    security_compliance_change_count: int = Field(ge=0)
    summary: dict[str, Any] = Field(default_factory=dict)
    content_id: str = ""
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identity_and_order(self) -> "MultiVariantReviewDiff":
        ordered = sorted(self.pairwise_diffs, key=lambda item: item.candidate_decision_id)
        if len({item.candidate_decision_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate review decision variants")
        if self.pairwise_diffs != ordered:
            object.__setattr__(self, "pairwise_diffs", ordered)
        expected_variants = [item.candidate_decision_id for item in ordered]
        if sorted(self.variant_decision_ids) != expected_variants:
            raise ValueError("review variant index mismatch")
        object.__setattr__(self, "variant_decision_ids", expected_variants)
        expected_content = canonical_digest("multi_variant_review_diff_content", self.deterministic_payload())
        expected_id = canonical_digest("multi_variant_review_diff", {"content_id": expected_content})
        if self.content_id and self.content_id != expected_content:
            raise ValueError("multi-variant diff content ID mismatch")
        if self.audit_id and self.audit_id != expected_id:
            raise ValueError("multi-variant diff ID mismatch")
        if not self.content_id:
            object.__setattr__(self, "content_id", expected_content)
        if not self.audit_id:
            object.__setattr__(self, "audit_id", expected_id)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        for field_name in ("audit_id", "content_id", "runtime_metadata"):
            data.pop(field_name, None)
        data["variant_decision_ids"] = sorted(data["variant_decision_ids"])
        data["pairwise_diffs"] = sorted(
            data["pairwise_diffs"], key=lambda item: item["candidate_decision_id"]
        )
        return data

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
