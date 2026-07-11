"""Typed schemas for deterministic review-decision provenance and replay."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from intentforge.assurance.schema import canonical_digest


REVIEW_PROVENANCE_SCHEMA_VERSION = "1.0"
REVIEW_EVALUATOR_VERSION = "1.0"
REVIEW_CHECK_REGISTRY_VERSION = "1.0"

SnapshotType = Literal[
    "review_policy",
    "assurance_case",
    "rule_registry",
    "capability_registry",
    "evidence_registry",
    "evidence_resolution",
    "check_registry",
    "decision_strategy",
    "audit_package_observation",
    "boundary_conditions",
]
ExecutionNodeType = Literal[
    "input_validation",
    "subject_resolution",
    "scope_validation",
    "evidence_resolution",
    "check_evaluation",
    "decision_precedence",
    "decision_assembly",
]
ExecutionNodeStatus = Literal[
    "completed",
    "passed",
    "failed",
    "unresolved",
    "not_applicable",
    "not_checked",
]
ProvenanceVerificationStatus = Literal["verified", "failed", "unsupported", "missing"]


class FrozenDecisionSnapshot(BaseModel):
    """Immutable deterministic input snapshot used by one review evaluation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    snapshot_id: str = ""
    snapshot_type: SnapshotType
    reference_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    payload: Any
    content_id: str = ""

    @model_validator(mode="after")
    def validate_identity(self) -> "FrozenDecisionSnapshot":
        expected_content = canonical_digest("decision_snapshot_content", self.payload)
        expected_id = canonical_digest(
            "decision_snapshot",
            {
                "snapshot_type": self.snapshot_type,
                "reference_id": self.reference_id,
                "version": self.version,
                "content_id": expected_content,
            },
        )
        if self.content_id and self.content_id != expected_content:
            raise ValueError(f"snapshot content ID mismatch: {self.reference_id}")
        if self.snapshot_id and self.snapshot_id != expected_id:
            raise ValueError(f"snapshot ID mismatch: {self.reference_id}")
        if not self.content_id:
            object.__setattr__(self, "content_id", expected_content)
        if not self.snapshot_id:
            object.__setattr__(self, "snapshot_id", expected_id)
        return self


class ReviewExecutionNode(BaseModel):
    """One ordered, inspectable step in the closed review execution chain."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    node_id: str = ""
    sequence: int = Field(..., ge=0)
    node_type: ExecutionNodeType
    node_key: str = Field(..., min_length=1)
    status: ExecutionNodeStatus
    input_content_ids: list[str] = Field(default_factory=list)
    output_content_ids: list[str] = Field(default_factory=list)
    check_id: str | None = None
    check_type: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    observed_value: Any = None
    expected_value: Any = None
    diagnostics: list[str] = Field(default_factory=list)
    content_id: str = ""

    @model_validator(mode="after")
    def validate_identity(self) -> "ReviewExecutionNode":
        payload = self.deterministic_payload()
        expected_content = canonical_digest("review_execution_node_content", payload)
        expected_id = canonical_digest(
            "review_execution_node",
            {"node_key": self.node_key, "sequence": self.sequence, "content_id": expected_content},
        )
        if self.content_id and self.content_id != expected_content:
            raise ValueError(f"execution node content ID mismatch: {self.node_key}")
        if self.node_id and self.node_id != expected_id:
            raise ValueError(f"execution node ID mismatch: {self.node_key}")
        if not self.content_id:
            object.__setattr__(self, "content_id", expected_content)
        if not self.node_id:
            object.__setattr__(self, "node_id", expected_id)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data.pop("node_id", None)
        data.pop("content_id", None)
        data["input_content_ids"] = sorted(data["input_content_ids"])
        data["output_content_ids"] = sorted(data["output_content_ids"])
        data["diagnostics"] = sorted(data["diagnostics"])
        return data


class DecisionProvenance(BaseModel):
    """Frozen execution inputs and ordered trace for deterministic replay."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    provenance_id: str = ""
    schema_version: str = REVIEW_PROVENANCE_SCHEMA_VERSION
    tool_version: str = Field(..., min_length=1)
    evaluator_version: str = REVIEW_EVALUATOR_VERSION
    check_registry_version: str = REVIEW_CHECK_REGISTRY_VERSION
    check_registry_content_id: str
    decision_strategy: str
    decision_strategy_content_id: str
    policy_snapshot_id: str
    assurance_case_snapshot_id: str
    snapshot_ids: list[str] = Field(default_factory=list)
    snapshots: list[FrozenDecisionSnapshot] = Field(..., min_length=1)
    execution_nodes: list[ReviewExecutionNode] = Field(..., min_length=1)
    active_boundary_conditions: dict[str, Any] = Field(default_factory=dict)
    evidence_definition_count: int = Field(ge=0)
    evidence_observation_count: int = Field(ge=0)
    content_id: str = ""
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_identity_and_ordering(self) -> "DecisionProvenance":
        ordered_snapshots = sorted(self.snapshots, key=lambda item: (item.snapshot_type, item.reference_id))
        ordered_nodes = sorted(self.execution_nodes, key=lambda item: (item.sequence, item.node_key))
        if len({item.snapshot_id for item in ordered_snapshots}) != len(ordered_snapshots):
            raise ValueError("duplicate provenance snapshot IDs")
        if len({item.node_id for item in ordered_nodes}) != len(ordered_nodes):
            raise ValueError("duplicate provenance execution node IDs")
        if len({item.sequence for item in ordered_nodes}) != len(ordered_nodes):
            raise ValueError("duplicate provenance execution sequence values")
        expected_snapshot_ids = [item.snapshot_id for item in ordered_snapshots]
        if self.snapshot_ids and self.snapshot_ids != expected_snapshot_ids:
            raise ValueError("provenance snapshot index mismatch")
        if not self.snapshot_ids:
            object.__setattr__(self, "snapshot_ids", expected_snapshot_ids)
        if self.snapshots != ordered_snapshots:
            object.__setattr__(self, "snapshots", ordered_snapshots)
        if self.execution_nodes != ordered_nodes:
            object.__setattr__(self, "execution_nodes", ordered_nodes)
        if self.policy_snapshot_id not in expected_snapshot_ids:
            raise ValueError("policy snapshot is missing from provenance")
        if self.assurance_case_snapshot_id not in expected_snapshot_ids:
            raise ValueError("assurance case snapshot is missing from provenance")
        expected_content = canonical_digest("decision_provenance_content", self.deterministic_payload())
        expected_id = canonical_digest("decision_provenance", {"content_id": expected_content})
        if self.content_id and self.content_id != expected_content:
            raise ValueError("decision provenance content ID mismatch")
        if self.provenance_id and self.provenance_id != expected_id:
            raise ValueError("decision provenance ID mismatch")
        if not self.content_id:
            object.__setattr__(self, "content_id", expected_content)
        if not self.provenance_id:
            object.__setattr__(self, "provenance_id", expected_id)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        for field_name in ("provenance_id", "content_id", "runtime_metadata"):
            data.pop(field_name, None)
        data["snapshot_ids"] = sorted(data["snapshot_ids"])
        data["snapshots"] = sorted(
            data["snapshots"], key=lambda item: (item["snapshot_type"], item["reference_id"])
        )
        data["execution_nodes"] = sorted(
            data["execution_nodes"], key=lambda item: (item["sequence"], item["node_key"])
        )
        return data

    def snapshot(self, snapshot_type: str) -> FrozenDecisionSnapshot:
        matches = [item for item in self.snapshots if item.snapshot_type == snapshot_type]
        if len(matches) != 1:
            raise ValueError(f"expected exactly one {snapshot_type} snapshot")
        return matches[0]


class DecisionProvenanceVerification(BaseModel):
    """Structured result of snapshot integrity and deterministic replay checks."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    status: ProvenanceVerificationStatus
    provenance_id: str | None = None
    replay_supported: bool = False
    replay_performed: bool = False
    replay_decision_id: str | None = None
    snapshot_count: int = 0
    execution_node_count: int = 0
    evidence_definition_count: int = 0
    evidence_observation_count: int = 0
    snapshot_mismatch_count: int = 0
    execution_node_mismatch_count: int = 0
    replay_mismatch_count: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)
