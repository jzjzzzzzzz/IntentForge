"""Schemas for engineering evidence traceability and trust reporting."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intentforge.knowledge.capability_schema import (
    CapabilityStage,
    SUPPORTED_CAPABILITY_FAMILIES,
    SUPPORTED_CAPABILITY_STAGES,
    stable_capability_digest,
)


EvidenceType = Literal[
    "rule_definition",
    "rule_pack",
    "parser_support",
    "intent_schema",
    "constraint_compiler",
    "cad_generator",
    "geometry_validator",
    "topology_inspector",
    "feature_recognizer",
    "knowledge_evaluator",
    "reasoning_case",
    "golden_case",
    "benchmark_case",
    "rejection_case",
    "regression_test",
    "technical_harness_gate",
    "documentation",
    "package_artifact",
]
EvidenceRole = Literal["implementation", "verification", "boundary", "limitation", "provenance", "packaging"]
EvidenceStatus = Literal[
    "verified",
    "failed",
    "unresolved",
    "unavailable",
    "stale",
    "not_checked",
    "not_applicable",
]
EvidenceBundleStatus = Literal[
    "evidence_complete",
    "evidence_partial",
    "evidence_failed",
    "evidence_unresolved",
    "boundary_verified",
    "not_applicable",
]

SUPPORTED_EVIDENCE_TYPES = (
    "rule_definition",
    "rule_pack",
    "parser_support",
    "intent_schema",
    "constraint_compiler",
    "cad_generator",
    "geometry_validator",
    "topology_inspector",
    "feature_recognizer",
    "knowledge_evaluator",
    "reasoning_case",
    "golden_case",
    "benchmark_case",
    "rejection_case",
    "regression_test",
    "technical_harness_gate",
    "documentation",
    "package_artifact",
)
SUPPORTED_EVIDENCE_ROLES = ("implementation", "verification", "boundary", "limitation", "provenance", "packaging")
SUPPORTED_EVIDENCE_STATUSES = (
    "verified",
    "failed",
    "unresolved",
    "unavailable",
    "stale",
    "not_checked",
    "not_applicable",
)
SUPPORTED_EVIDENCE_BUNDLE_STATUSES = (
    "evidence_complete",
    "evidence_partial",
    "evidence_failed",
    "evidence_unresolved",
    "boundary_verified",
    "not_applicable",
)
EVIDENCE_SCHEMA_VERSION = "1.0"
FIXED_EVIDENCE_TIMESTAMP = "2026-07-10T00:00:00+00:00"


def stable_evidence_digest(prefix: str, payload: dict[str, Any]) -> str:
    """Return a deterministic hash ID for evidence reports and observations."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:12]}"


def _normalized_reference(value: str) -> str:
    normalized = unquote(value.strip()).replace("\\", "/")
    if not normalized:
        raise ValueError("reference must be non-empty")
    if normalized.startswith("/") or normalized.startswith("~"):
        raise ValueError("reference must not be absolute")
    parts = [part for part in normalized.split("/") if part]
    if any(part == ".." for part in parts) or normalized in {".", ".."}:
        raise ValueError("reference must not contain path traversal")
    return normalized


def _validate_id(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    if not normalized[0].islower():
        raise ValueError(f"{field_name} must start with a lowercase letter")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_")
    if any(character not in allowed for character in normalized):
        raise ValueError(f"{field_name} must contain only lowercase letters, digits, and underscores")
    return normalized


class EvidenceDefinition(BaseModel):
    """Declarative evidence metadata connected to capabilities, rules, and packs."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    evidence_id: str
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    evidence_type: EvidenceType
    role: EvidenceRole
    reference: str
    family: str | None = None
    stages: list[CapabilityStage] = Field(default_factory=list)
    capability_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    pack_ids: list[str] = Field(default_factory=list)
    verification_method: str = Field(default="static_resolution", min_length=1)
    expected_result: str = Field(default="reference_resolves", min_length=1)
    required: bool = True
    provenance: dict[str, Any] = Field(default_factory=dict)
    version: str = Field(default="1.0", min_length=1)
    limitations: list[str] = Field(default_factory=list)
    freshness_policy: str = Field(default="version_match", min_length=1)
    reuse_reason: str = ""

    @field_validator("evidence_id")
    @classmethod
    def validate_evidence_id(cls, value: str) -> str:
        return _validate_id(value, "evidence_id")

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        return _normalized_reference(value)

    @field_validator("family")
    @classmethod
    def validate_family(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_CAPABILITY_FAMILIES:
            raise ValueError(f"unsupported evidence family: {value}")
        return value

    @field_validator("capability_ids", "rule_ids", "pack_ids", "limitations")
    @classmethod
    def validate_string_list(cls, value: list[str]) -> list[str]:
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise ValueError("list entries must be non-empty strings")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not all(part.isdigit() for part in value.split(".")):
            raise ValueError("version must use numeric dot notation")
        return value

    @model_validator(mode="after")
    def validate_role_semantics(self) -> "EvidenceDefinition":
        if self.role == "limitation" and not self.limitations:
            raise ValueError("limitation evidence must include limitations")
        if self.role == "boundary" and self.evidence_type != "rejection_case":
            raise ValueError("boundary evidence must use rejection_case evidence_type")
        return self

    @property
    def normalized_reference(self) -> str:
        return self.reference

    def content_identity(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "role": self.role,
            "reference": self.reference,
            "family": self.family,
            "stages": list(self.stages),
            "capability_ids": list(self.capability_ids),
            "rule_ids": list(self.rule_ids),
            "pack_ids": list(self.pack_ids),
            "version": self.version,
            "required": self.required,
            "expected_result": self.expected_result,
        }


class EvidenceManifest(BaseModel):
    """Packaged manifest of evidence definitions."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    manifest_version: str = Field(default=EVIDENCE_SCHEMA_VERSION, min_length=1)
    generated_by: str = Field(default="intentforge", min_length=1)
    evidence: list[EvidenceDefinition] = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("manifest_version")
    @classmethod
    def validate_manifest_version(cls, value: str) -> str:
        if not all(part.isdigit() for part in value.split(".")):
            raise ValueError("manifest_version must use numeric dot notation")
        return value

    @model_validator(mode="after")
    def validate_unique_evidence_ids(self) -> "EvidenceManifest":
        seen: set[str] = set()
        duplicates: list[str] = []
        for definition in self.evidence:
            if definition.evidence_id in seen:
                duplicates.append(definition.evidence_id)
            seen.add(definition.evidence_id)
        if duplicates:
            raise ValueError(f"duplicate evidence ids: {', '.join(sorted(set(duplicates)))}")
        return self


class EvidenceObservation(BaseModel):
    """Resolved or verified observation for one evidence definition."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    status: EvidenceStatus
    resolved_reference: str
    observed_result: str
    expected_result: str
    matches_expectation: bool
    family: str | None = None
    stages: list[CapabilityStage] = Field(default_factory=list)
    verifier: str
    diagnostics: list[str] = Field(default_factory=list)
    content_id: str
    source_version: str
    capability_ids: list[str] = Field(default_factory=list)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)

    def deterministic_payload(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "status": self.status,
            "resolved_reference": self.resolved_reference,
            "observed_result": self.observed_result,
            "expected_result": self.expected_result,
            "matches_expectation": self.matches_expectation,
            "family": self.family,
            "stages": list(self.stages),
            "verifier": self.verifier,
            "diagnostics": list(self.diagnostics),
            "source_version": self.source_version,
            "capability_ids": list(self.capability_ids),
        }


class EvidenceBundle(BaseModel):
    """Evidence bundle assembled for a single declared capability."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: str
    capability_id: str
    family: str
    capability_status: str
    implementation_evidence: list[EvidenceObservation] = Field(default_factory=list)
    verification_evidence: list[EvidenceObservation] = Field(default_factory=list)
    boundary_evidence: list[EvidenceObservation] = Field(default_factory=list)
    limitation_evidence: list[EvidenceObservation] = Field(default_factory=list)
    provenance_evidence: list[EvidenceObservation] = Field(default_factory=list)
    packaging_evidence: list[EvidenceObservation] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    resolved_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_evidence_ids: list[str] = Field(default_factory=list)
    failed_evidence_ids: list[str] = Field(default_factory=list)
    stale_evidence_ids: list[str] = Field(default_factory=list)
    evidence_completeness: float
    bundle_status: EvidenceBundleStatus
    diagnostics: list[str] = Field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


class EvidenceValidationResult(BaseModel):
    """Structured evidence manifest validation result."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    evidence_checked: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


class EvidenceResolutionReport(BaseModel):
    """Deterministic report of evidence resolution or verification observations."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    generated_at: str
    runtime_verification: bool
    evidence_count: int
    observations: list[EvidenceObservation]
    summary: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


class TrustReport(BaseModel):
    """Deterministic evidence trust report for declared IntentForge capabilities."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    generated_at: str
    manifest_version: str
    declared_capability_count: int
    supported_capability_count: int
    partially_supported_capability_count: int
    unsupported_boundary_count: int
    total_evidence_definition_count: int
    required_evidence_count: int
    verified_evidence_count: int
    failed_evidence_count: int
    unresolved_evidence_count: int
    unavailable_evidence_count: int
    stale_evidence_count: int
    orphan_evidence_count: int
    duplicate_evidence_id_count: int
    duplicate_normalized_reference_count: int
    family_mismatch_count: int
    stage_mismatch_count: int
    capability_mismatch_count: int
    unknown_rule_reference_count: int
    unknown_pack_reference_count: int
    unknown_capability_reference_count: int
    supported_capabilities_with_complete_evidence: list[str] = Field(default_factory=list)
    supported_capabilities_with_incomplete_evidence: list[str] = Field(default_factory=list)
    partially_supported_capabilities_with_complete_limitation_evidence: list[str] = Field(default_factory=list)
    partially_supported_capabilities_missing_limitation_evidence: list[str] = Field(default_factory=list)
    unsupported_boundaries_with_verified_rejection_evidence: list[str] = Field(default_factory=list)
    unsupported_boundaries_missing_rejection_evidence: list[str] = Field(default_factory=list)
    implementation_evidence_completeness: dict[str, Any]
    verification_evidence_completeness: dict[str, Any]
    boundary_evidence_completeness: dict[str, Any]
    limitation_evidence_completeness: dict[str, Any]
    per_family: dict[str, dict[str, int]] = Field(default_factory=dict)
    per_stage: dict[str, dict[str, int]] = Field(default_factory=dict)
    per_evidence_type: dict[str, dict[str, int]] = Field(default_factory=dict)
    per_evidence_role: dict[str, dict[str, int]] = Field(default_factory=dict)
    bundles: list[EvidenceBundle] = Field(default_factory=list)
    observations: list[EvidenceObservation] = Field(default_factory=list)
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    validation_warnings: list[dict[str, Any]] = Field(default_factory=list)
    overall_trust_gate_passed: bool
    summary: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def fixed_evidence_timestamp() -> str:
    """Return the fixed timestamp used in deterministic evidence reports."""

    return FIXED_EVIDENCE_TIMESTAMP


def make_observation(
    definition: EvidenceDefinition,
    *,
    status: EvidenceStatus,
    observed_result: str,
    matches_expectation: bool,
    verifier: str,
    diagnostics: list[str] | None = None,
    runtime_metadata: dict[str, Any] | None = None,
) -> EvidenceObservation:
    """Create an observation with a deterministic content ID."""

    payload = {
        "evidence_id": definition.evidence_id,
        "status": status,
        "resolved_reference": definition.reference,
        "observed_result": observed_result,
        "expected_result": definition.expected_result,
        "matches_expectation": matches_expectation,
        "family": definition.family,
        "stages": list(definition.stages),
        "verifier": verifier,
        "diagnostics": diagnostics or [],
        "source_version": definition.version,
        "capability_ids": list(definition.capability_ids),
    }
    content_id = stable_evidence_digest("evidence_obs", payload)
    return EvidenceObservation(
        **payload,
        content_id=content_id,
        runtime_metadata=runtime_metadata or {},
    )


def make_bundle_id(payload: dict[str, Any]) -> str:
    """Create a deterministic bundle identifier."""

    return stable_capability_digest("evidence_bundle", payload)
