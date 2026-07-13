"""Stable schemas for scoped engineering assurance records."""

from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any, Literal
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AssuranceProfile = Literal["static", "standard", "full"]
AssuranceClaimType = Literal[
    "request_interpreted", "intent_schema_valid", "family_supported",
    "feature_plan_supported", "constraints_compiled", "engineering_rules_evaluated",
    "geometry_generated", "geometry_valid", "topology_inspected", "features_recognized",
    "engineering_reasoning_completed", "requested_edit_preserved_intent",
    "unsupported_behavior_rejected", "capability_evidence_available",
    "artifact_integrity_verified", "package_reproducible", "limitation_disclosed",
]
AssuranceClaimStatus = Literal[
    "supported", "partially_supported", "unsupported", "failed", "unresolved", "not_applicable"
]
AssuranceCaseStatus = Literal[
    "assurance_complete", "assurance_complete_with_limitations", "assurance_partial",
    "assurance_failed", "assurance_unresolved",
]
ValidationObservationStatus = Literal["passed", "failed", "warning", "not_checked", "unresolved"]
LimitationSignificance = Literal[
    "informational", "partial_support", "unsupported_boundary", "external_review_required"
]

SCHEMA_VERSION = "1.0"
SUPPORTED_FAMILIES = {"wall_mounted_bracket", "l_bracket", "industrial_flange"}
FORBIDDEN_PATH_PARTS = {".git", ".claude", "CLAUDE.md"}
CONTENT_ADDRESS_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_digest(prefix: str, payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def validate_content_address(value: str | None) -> str | None:
    if value is not None and not CONTENT_ADDRESS_PATTERN.fullmatch(value):
        raise ValueError("content address must use sha256:<64 lowercase hex characters>")
    return value


def safe_relative_path(value: str) -> str:
    decoded = value.replace("\\", "/")
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    path = PurePosixPath(decoded)
    if (
        not decoded
        or path.is_absolute()
        or decoded.startswith("//")
        or re.match(r"^[A-Za-z]:/", decoded)
        or ".." in path.parts
    ):
        raise ValueError("artifact path must be a safe relative path")
    if any(part in FORBIDDEN_PATH_PARTS for part in path.parts):
        raise ValueError("artifact path contains a forbidden component")
    return path.as_posix()


class AssuranceArgument(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    argument_id: str
    claim_id: str
    rationale_code: str
    rationale: str
    rule_ids: list[str] = Field(default_factory=list)
    capability_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    validation_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    limitation_ids: list[str] = Field(default_factory=list)
    parent_argument_ids: list[str] = Field(default_factory=list)
    predecessor_hash_pointer: str | None = None
    content_id: str

    @field_validator("predecessor_hash_pointer")
    @classmethod
    def valid_predecessor(cls, value: str | None) -> str | None:
        return validate_content_address(value)


class AssuranceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    claim_id: str
    claim_type: AssuranceClaimType
    title: str
    statement: str
    status: AssuranceClaimStatus
    family: str
    stages: list[str] = Field(default_factory=list)
    argument_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    supporting_validation_ids: list[str] = Field(default_factory=list)
    supporting_artifact_ids: list[str] = Field(default_factory=list)
    capability_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    required_review: bool = False
    provenance: str = "IntentForge deterministic assurance builder"
    version: str = "1.0"
    predecessor_hash_pointer: str | None = None
    content_id: str

    @field_validator("family")
    @classmethod
    def known_family(cls, value: str) -> str:
        from intentforge.schemas.family import validate_registered_family

        return validate_registered_family(value)

    @field_validator("predecessor_hash_pointer")
    @classmethod
    def valid_predecessor(cls, value: str | None) -> str | None:
        return validate_content_address(value)


class ValidationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    validation_id: str
    validation_type: str
    status: ValidationObservationStatus
    observed_result: Any = None
    expected_result: Any = None
    diagnostics: list[str] = Field(default_factory=list)
    source_report_id: str | None = None
    family: str
    stages: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    content_id: str


class LimitationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    limitation_id: str
    title: str
    description: str
    family: str
    capability_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    significance: LimitationSignificance
    review_required: bool = False
    source: str
    content_id: str


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    artifact_id: str
    artifact_type: str
    logical_name: str
    path: str
    content_hash: str | None = None
    size: int | None = Field(default=None, ge=0)
    producer_operation: str
    family: str
    request_id: str | None = None
    run_id: str | None = None
    validation_status: str = "not_checked"
    metadata_id: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return safe_relative_path(value)


class AssuranceCase(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    assurance_case_id: str
    schema_version: str = SCHEMA_VERSION
    profile: AssuranceProfile
    operation: str
    request_id: str
    run_id: str | None = None
    parent_run_id: str | None = None
    predecessor_hash_pointer: str | None = None
    input_request: dict[str, Any]
    structured_intent: dict[str, Any] | None = None
    cad_family: str
    feature_plan_summary: dict[str, Any] = Field(default_factory=dict)
    compiled_constraint_summary: list[dict[str, Any]] = Field(default_factory=list)
    rule_references: list[dict[str, Any]] = Field(default_factory=list)
    capability_references: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    claims: list[AssuranceClaim] = Field(default_factory=list)
    arguments: list[AssuranceArgument] = Field(default_factory=list)
    validation_observations: list[ValidationObservation] = Field(default_factory=list)
    artifact_records: list[ArtifactRecord] = Field(default_factory=list)
    limitations: list[LimitationRecord] = Field(default_factory=list)
    review_requirements: list[str] = Field(default_factory=list)
    reproducibility_metadata: dict[str, Any] = Field(default_factory=dict)
    reasoning_summary: dict[str, Any] | None = None
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)
    content_id: str
    overall_assurance_status: AssuranceCaseStatus

    @field_validator("predecessor_hash_pointer")
    @classmethod
    def valid_predecessor(cls, value: str | None) -> str | None:
        return validate_content_address(value)

    @model_validator(mode="after")
    def validate_unique_references(self) -> "AssuranceCase":
        for label, values in (("claim", self.claims), ("argument", self.arguments),
                              ("validation", self.validation_observations), ("artifact", self.artifact_records),
                              ("limitation", self.limitations)):
            attr = f"{label}_id" if label != "artifact" else "artifact_id"
            ids = [getattr(item, attr) for item in values]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {label} ids")
        argument_ids = {item.argument_id for item in self.arguments}
        for argument in self.arguments:
            unknown = set(argument.parent_argument_ids) - argument_ids
            if unknown:
                raise ValueError(f"unknown parent argument ids: {', '.join(sorted(unknown))}")
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        for field_name in (
            "assurance_case_id", "content_id", "runtime_metadata", "request_id", "run_id", "parent_run_id",
        ):
            data.pop(field_name, None)
        if data.get("predecessor_hash_pointer") is None:
            data.pop("predecessor_hash_pointer", None)
        for claim in data.get("claims", []):
            if claim.get("predecessor_hash_pointer") is None:
                claim.pop("predecessor_hash_pointer", None)
        for argument in data.get("arguments", []):
            if argument.get("predecessor_hash_pointer") is None:
                argument.pop("predecessor_hash_pointer", None)
        for artifact in data.get("artifact_records", []):
            artifact.pop("request_id", None)
            artifact.pop("run_id", None)
            artifact.pop("content_hash", None)
            artifact.pop("size", None)
            artifact.pop("metadata_id", None)
        return data

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


class AssuranceValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)


def compute_assurance_content_id(case: AssuranceCase | dict[str, Any]) -> str:
    record = case if isinstance(case, AssuranceCase) else AssuranceCase.model_validate(case)
    return canonical_digest("assurance_content", record.deterministic_payload())


def serialize_assurance_case(case: AssuranceCase | dict[str, Any]) -> str:
    record = case if isinstance(case, AssuranceCase) else AssuranceCase.model_validate(case)
    return record.to_json()


def load_assurance_case(path: str | PurePosixPath) -> AssuranceCase:
    from pathlib import Path
    return AssuranceCase.model_validate_json(Path(path).read_text(encoding="utf-8"))
