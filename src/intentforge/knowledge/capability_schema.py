"""Stable schemas for engineering capability declarations and coverage."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CapabilityStatus = Literal["supported", "partially_supported", "unsupported", "not_applicable"]
CapabilityStage = Literal[
    "parsing",
    "intent_schema",
    "knowledge",
    "constraint_compilation",
    "cad_generation",
    "geometry_validation",
    "topology_inspection",
    "feature_recognition",
    "engineering_reasoning",
    "golden_verification",
    "rejection",
]
EvidenceType = Literal[
    "rule",
    "parser",
    "schema",
    "generator",
    "validator",
    "topology_metric",
    "feature_recognizer",
    "reasoning_case",
    "golden_case",
    "benchmark_case",
    "test",
    "rejection_case",
    "documentation",
]

SUPPORTED_CAPABILITY_STATUSES = ("supported", "partially_supported", "unsupported", "not_applicable")
SUPPORTED_CAPABILITY_STAGES = (
    "parsing",
    "intent_schema",
    "knowledge",
    "constraint_compilation",
    "cad_generation",
    "geometry_validation",
    "topology_inspection",
    "feature_recognition",
    "engineering_reasoning",
    "golden_verification",
    "rejection",
)
SUPPORTED_EVIDENCE_TYPES = (
    "rule",
    "parser",
    "schema",
    "generator",
    "validator",
    "topology_metric",
    "feature_recognizer",
    "reasoning_case",
    "golden_case",
    "benchmark_case",
    "test",
    "rejection_case",
    "documentation",
)
SUPPORTED_CAPABILITY_FAMILIES = ("wall_mounted_bracket", "l_bracket")


def stable_capability_digest(prefix: str, payload: dict[str, Any]) -> str:
    """Return a deterministic content hash for capability reports."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:12]}"


def _validate_reference_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("reference must be non-empty")
    if normalized.startswith("/") or "\\.." in normalized or "../" in normalized or normalized == "..":
        raise ValueError("reference must not be absolute or contain path traversal")
    return normalized


class EvidenceReference(BaseModel):
    """Identifier-only evidence reference for a declared capability."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    evidence_type: EvidenceType
    reference: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    required: bool = True
    family: str | None = None
    stage: CapabilityStage | None = None

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        return _validate_reference_text(value)

    @field_validator("family")
    @classmethod
    def validate_family(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_CAPABILITY_FAMILIES:
            raise ValueError(f"unsupported evidence family: {value}")
        return value


class CapabilityDefinition(BaseModel):
    """Declarative product capability with traceable implementation and verification evidence."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    capability_id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    family: str
    status: CapabilityStatus
    stages: list[CapabilityStage] = Field(..., min_length=1)
    rule_ids: list[str] = Field(default_factory=list)
    knowledge_packs: list[str] = Field(default_factory=list)
    implementation_evidence: list[EvidenceReference] = Field(default_factory=list)
    verification_evidence: list[EvidenceReference] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    rejection_behavior: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    version: str = Field(default="1.0", min_length=1)

    @field_validator("family")
    @classmethod
    def validate_family(cls, value: str) -> str:
        if value not in SUPPORTED_CAPABILITY_FAMILIES:
            raise ValueError(f"unsupported capability family: {value}")
        return value

    @field_validator("rule_ids", "knowledge_packs", "limitations")
    @classmethod
    def validate_string_list(cls, value: list[str]) -> list[str]:
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError("list entries must be non-empty strings")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        parts = value.split(".")
        if not parts or not all(part.isdigit() for part in parts):
            raise ValueError("version must use numeric dot notation, for example '1.0'")
        return value

    @model_validator(mode="after")
    def validate_status_requirements(self) -> "CapabilityDefinition":
        if self.status == "partially_supported" and not self.limitations:
            raise ValueError("partially supported capabilities require explicit limitations")
        if self.status == "unsupported" and not self.rejection_behavior.strip():
            raise ValueError("unsupported capabilities require rejection_behavior")
        return self


class CapabilityManifest(BaseModel):
    """Packaged capability manifest for IntentForge engineering support claims."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    manifest_version: str = Field(default="1.0", min_length=1)
    generated_by: str = Field(default="intentforge")
    capabilities: list[CapabilityDefinition] = Field(..., min_length=1)
    cross_cutting_rules: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_capabilities(self) -> "CapabilityManifest":
        seen: set[str] = set()
        duplicates: list[str] = []
        for capability in self.capabilities:
            if capability.capability_id in seen:
                duplicates.append(capability.capability_id)
            seen.add(capability.capability_id)
        if duplicates:
            raise ValueError(f"duplicate capability ids: {', '.join(sorted(set(duplicates)))}")
        return self


class CapabilityMatrixRow(BaseModel):
    """Flattened capability matrix row for filtering and external tools."""

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    title: str
    family: str
    status: CapabilityStatus
    stages: list[CapabilityStage]
    knowledge_packs: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    implementation_evidence_count: int
    verification_evidence_count: int
    limitations: list[str] = Field(default_factory=list)
    rejection_behavior: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    version: str


class CapabilityMatrix(BaseModel):
    """Deterministic matrix of declared capabilities."""

    model_config = ConfigDict(extra="forbid")

    matrix_id: str
    generated_at: str
    rows: list[CapabilityMatrixRow]
    filters: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


class CoverageReport(BaseModel):
    """Deterministic coverage report for engineering capability claims."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    generated_at: str
    declared_capability_count: int
    supported_capability_count: int
    partially_supported_capability_count: int
    unsupported_capability_count: int
    not_applicable_capability_count: int
    active_rule_count: int
    mapped_active_rule_count: int
    orphan_active_rule_count: int
    implementation_evidence_completeness: float
    verification_evidence_completeness: float
    supported_capabilities_missing_implementation_evidence: list[str] = Field(default_factory=list)
    supported_capabilities_missing_verification_evidence: list[str] = Field(default_factory=list)
    partial_capabilities_missing_limitations: list[str] = Field(default_factory=list)
    unsupported_capabilities_missing_rejection_or_boundary_evidence: list[str] = Field(default_factory=list)
    unknown_rule_references: list[str] = Field(default_factory=list)
    unknown_pack_references: list[str] = Field(default_factory=list)
    unknown_evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_capability_ids: list[str] = Field(default_factory=list)
    duplicate_evidence_references: list[dict[str, Any]] = Field(default_factory=list)
    orphan_active_rules: list[str] = Field(default_factory=list)
    cross_cutting_rules: dict[str, str] = Field(default_factory=dict)
    per_family: dict[str, dict[str, int]] = Field(default_factory=dict)
    per_stage: dict[str, dict[str, int]] = Field(default_factory=dict)
    matrix: list[CapabilityMatrixRow] = Field(default_factory=list)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    validation_warnings: list[dict[str, Any]] = Field(default_factory=list)
    passed: bool

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def fixed_coverage_timestamp() -> str:
    """Return a stable default timestamp used for deterministic report IDs."""

    return datetime(2026, 7, 10, 0, 0, 0).isoformat() + "+00:00"
