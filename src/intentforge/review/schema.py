"""Typed schemas for deterministic engineering review policies and decisions."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, field_validator, model_validator

from intentforge.assurance.schema import (
    AssuranceCaseStatus,
    AssuranceClaimStatus,
    AssuranceClaimType,
    AssuranceProfile,
    LimitationSignificance,
    ValidationObservationStatus,
    canonical_digest,
    validate_content_address,
)
from intentforge.knowledge.evidence_schema import EvidenceStatus
from intentforge.review.provenance_schema import DecisionProvenance


REVIEW_SCHEMA_VERSION = "1.0"
SUPPORTED_POLICY_FAMILIES = (
    "wall_mounted_bracket", "l_bracket", "industrial_flange", "spur_gear", "standard_bolt",
)
SUPPORTED_POLICY_OPERATIONS = (
    "parse",
    "parse_build",
    "edit_parse",
    "edit_parse_apply",
    "design_review",
)
SUPPORTED_ASSURANCE_PROFILES = ("static", "standard", "full")
SUPPORTED_ASSURANCE_STATUSES = (
    "assurance_complete",
    "assurance_complete_with_limitations",
    "assurance_partial",
    "assurance_failed",
    "assurance_unresolved",
)
SUPPORTED_CLAIM_TYPES = (
    "request_interpreted",
    "intent_schema_valid",
    "family_supported",
    "feature_plan_supported",
    "constraints_compiled",
    "engineering_rules_evaluated",
    "geometry_generated",
    "geometry_valid",
    "topology_inspected",
    "features_recognized",
    "engineering_reasoning_completed",
    "requested_edit_preserved_intent",
    "unsupported_behavior_rejected",
    "capability_evidence_available",
    "artifact_integrity_verified",
    "package_reproducible",
    "limitation_disclosed",
)
SUPPORTED_CLAIM_STATUSES = (
    "supported",
    "partially_supported",
    "unsupported",
    "failed",
    "unresolved",
    "not_applicable",
)
SUPPORTED_VALIDATION_TYPES = (
    "geometry_validation",
    "topology_inspection",
    "feature_recognition",
)
SUPPORTED_VALIDATION_STATUSES = ("passed", "failed", "warning", "not_checked", "unresolved")
SUPPORTED_LIMITATION_CATEGORIES = (
    "informational",
    "partial_support",
    "unsupported_boundary",
    "external_review_required",
)

PolicyScope = Literal["assurance_case", "assurance_case_and_audit_package"]
PolicySubjectType = Literal["design_result", "edit_result", "safe_rejection", "audit_package"]
PolicyCheckType = Literal[
    "assurance_profile_allowed",
    "overall_assurance_status_allowed",
    "required_claim_present",
    "required_claim_status",
    "forbidden_claim_status",
    "maximum_partial_claim_count",
    "zero_failed_claims",
    "zero_unresolved_claims",
    "required_validation_present",
    "required_validation_status",
    "required_evidence_status",
    "required_capability_reference",
    "required_rule_reference",
    "artifact_integrity_required",
    "audit_package_valid",
    "reproducibility_required",
    "limitation_category_allowed",
    "limitation_category_forbidden",
    "limitation_requires_manual_review",
    "unsupported_boundary_disclosed",
    "safe_rejection_verified",
    "no_cad_artifact_on_rejection",
    "edit_intent_preservation_required",
    "required_review_disclosed",
    "minimum_assurance_profile",
    "schema_version_supported",
]
PolicyCheckSeverity = Literal["informational", "warning", "conditional", "manual_review", "blocking"]
PolicyCheckStatus = Literal["passed", "failed", "unresolved", "not_applicable", "not_checked"]
ReviewDecisionStatus = Literal[
    "accepted_within_declared_scope",
    "accepted_with_conditions",
    "accepted_with_exemption",
    "manual_review_required",
    "rejected_by_policy",
    "unresolved",
]
# ``EXEMPTION_*`` constants live in ``intentforge.review.exemption_schema`` to
# avoid a circular import, but they are re-exported below for the namespace
# contract of ``intentforge.review.schema``.
EXEMPTION_SCHEMA_VERSION = "1.0"
EXEMPTION_CONDITION_TYPE = "policy_acknowledgement_required"
SUPPORTED_EXEMPTION_TARGET_KINDS = ("rule_id", "metric", "parameter")
SUPPORTED_EXEMPTION_COMPARATORS = ("eq", "lt", "le", "gt", "ge")
ConditionType = Literal[
    "additional_validation_required",
    "external_review_required",
    "limitation_acknowledgement_required",
    "artifact_integrity_required",
    "reproducibility_check_required",
    "unsupported_scope_correction_required",
    "intent_clarification_required",
    "policy_acknowledgement_required",
]

SUPPORTED_POLICY_SCOPES = ("assurance_case", "assurance_case_and_audit_package")
SUPPORTED_SUBJECT_TYPES = ("design_result", "edit_result", "safe_rejection", "audit_package")
SUPPORTED_CHECK_TYPES = (
    "assurance_profile_allowed",
    "overall_assurance_status_allowed",
    "required_claim_present",
    "required_claim_status",
    "forbidden_claim_status",
    "maximum_partial_claim_count",
    "zero_failed_claims",
    "zero_unresolved_claims",
    "required_validation_present",
    "required_validation_status",
    "required_evidence_status",
    "required_capability_reference",
    "required_rule_reference",
    "artifact_integrity_required",
    "audit_package_valid",
    "reproducibility_required",
    "limitation_category_allowed",
    "limitation_category_forbidden",
    "limitation_requires_manual_review",
    "unsupported_boundary_disclosed",
    "safe_rejection_verified",
    "no_cad_artifact_on_rejection",
    "edit_intent_preservation_required",
    "required_review_disclosed",
    "minimum_assurance_profile",
    "schema_version_supported",
)
SUPPORTED_CHECK_SEVERITIES = ("informational", "warning", "conditional", "manual_review", "blocking")
SUPPORTED_CHECK_STATUSES = ("passed", "failed", "unresolved", "not_applicable", "not_checked")
SUPPORTED_DECISION_STATUSES = (
    "accepted_within_declared_scope",
    "accepted_with_conditions",
    "accepted_with_exemption",
    "manual_review_required",
    "rejected_by_policy",
    "unresolved",
)
SUPPORTED_CONDITION_TYPES = (
    EXEMPTION_CONDITION_TYPE,
    "additional_validation_required",
    "external_review_required",
    "limitation_acknowledgement_required",
    "artifact_integrity_required",
    "reproducibility_check_required",
    "unsupported_scope_correction_required",
    "intent_clarification_required",
)


class CheckParameters(BaseModel):
    """Base class for closed, type-specific policy check parameters."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EmptyCheckParameters(CheckParameters):
    pass


class AssuranceProfileAllowedParameters(CheckParameters):
    allowed_profiles: list[AssuranceProfile] = Field(..., min_length=1)


class OverallAssuranceStatusAllowedParameters(CheckParameters):
    allowed_statuses: list[AssuranceCaseStatus] = Field(..., min_length=1)


class RequiredClaimPresentParameters(CheckParameters):
    claim_types: list[AssuranceClaimType] = Field(..., min_length=1)


class RequiredClaimStatusParameters(CheckParameters):
    claim_types: list[AssuranceClaimType] = Field(..., min_length=1)
    allowed_statuses: list[AssuranceClaimStatus] = Field(..., min_length=1)


class ForbiddenClaimStatusParameters(CheckParameters):
    forbidden_statuses: list[AssuranceClaimStatus] = Field(..., min_length=1)


class MaximumPartialClaimCountParameters(CheckParameters):
    maximum: int = Field(..., ge=0)


class RequiredValidationPresentParameters(CheckParameters):
    validation_types: list[str] = Field(..., min_length=1)

    @field_validator("validation_types")
    @classmethod
    def known_validation_types(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(SUPPORTED_VALIDATION_TYPES))
        if unknown:
            raise ValueError(f"unsupported validation types: {', '.join(unknown)}")
        return value


class RequiredValidationStatusParameters(CheckParameters):
    validation_types: list[str] = Field(..., min_length=1)
    allowed_statuses: list[ValidationObservationStatus] = Field(..., min_length=1)

    @field_validator("validation_types")
    @classmethod
    def known_validation_types(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(SUPPORTED_VALIDATION_TYPES))
        if unknown:
            raise ValueError(f"unsupported validation types: {', '.join(unknown)}")
        return value


class RequiredEvidenceStatusParameters(CheckParameters):
    evidence_ids: list[str] = Field(default_factory=list)
    allowed_statuses: list[EvidenceStatus] = Field(default_factory=lambda: ["verified"])


class RequiredCapabilityReferenceParameters(CheckParameters):
    capability_ids: list[str] = Field(..., min_length=1)


class RequiredRuleReferenceParameters(CheckParameters):
    rule_ids: list[str] = Field(..., min_length=1)


class ArtifactIntegrityRequiredParameters(CheckParameters):
    require_artifacts: bool = True
    require_all_hashed: bool = True
    require_integrity_claim: bool = True


class AuditPackageValidParameters(CheckParameters):
    require_package: bool = True


class ReproducibilityRequiredParameters(CheckParameters):
    require_deterministic_metadata: bool = True
    require_valid_audit_package: bool = True


class LimitationCategoryParameters(CheckParameters):
    categories: list[LimitationSignificance] = Field(..., min_length=1)
    capability_ids: list[str] = Field(default_factory=list)
    only_when_exercised: bool = False


class UnsupportedBoundaryDisclosedParameters(CheckParameters):
    minimum_count: int = Field(default=1, ge=0)


class SafeRejectionVerifiedParameters(CheckParameters):
    require_structured_error: bool = True
    require_boundary: bool = True
    require_rejection_evidence: bool = True


class NoCadArtifactOnRejectionParameters(CheckParameters):
    forbid_geometry_claims: bool = True


class EditIntentPreservationRequiredParameters(CheckParameters):
    require_parent_run_id: bool = False
    require_change_trace: bool = True
    require_preservation_trace: bool = True


class RequiredReviewDisclosedParameters(CheckParameters):
    minimum_count: int = Field(default=1, ge=1)


class MinimumAssuranceProfileParameters(CheckParameters):
    minimum_profile: AssuranceProfile


class SchemaVersionSupportedParameters(CheckParameters):
    supported_versions: list[str] = Field(default_factory=lambda: ["1.0"], min_length=1)


CHECK_PARAMETER_MODELS: dict[str, type[CheckParameters]] = {
    "assurance_profile_allowed": AssuranceProfileAllowedParameters,
    "overall_assurance_status_allowed": OverallAssuranceStatusAllowedParameters,
    "required_claim_present": RequiredClaimPresentParameters,
    "required_claim_status": RequiredClaimStatusParameters,
    "forbidden_claim_status": ForbiddenClaimStatusParameters,
    "maximum_partial_claim_count": MaximumPartialClaimCountParameters,
    "zero_failed_claims": EmptyCheckParameters,
    "zero_unresolved_claims": EmptyCheckParameters,
    "required_validation_present": RequiredValidationPresentParameters,
    "required_validation_status": RequiredValidationStatusParameters,
    "required_evidence_status": RequiredEvidenceStatusParameters,
    "required_capability_reference": RequiredCapabilityReferenceParameters,
    "required_rule_reference": RequiredRuleReferenceParameters,
    "artifact_integrity_required": ArtifactIntegrityRequiredParameters,
    "audit_package_valid": AuditPackageValidParameters,
    "reproducibility_required": ReproducibilityRequiredParameters,
    "limitation_category_allowed": LimitationCategoryParameters,
    "limitation_category_forbidden": LimitationCategoryParameters,
    "limitation_requires_manual_review": LimitationCategoryParameters,
    "unsupported_boundary_disclosed": UnsupportedBoundaryDisclosedParameters,
    "safe_rejection_verified": SafeRejectionVerifiedParameters,
    "no_cad_artifact_on_rejection": NoCadArtifactOnRejectionParameters,
    "edit_intent_preservation_required": EditIntentPreservationRequiredParameters,
    "required_review_disclosed": RequiredReviewDisclosedParameters,
    "minimum_assurance_profile": MinimumAssuranceProfileParameters,
    "schema_version_supported": SchemaVersionSupportedParameters,
}


class PolicyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    check_id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    check_type: PolicyCheckType
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    severity: PolicyCheckSeverity
    required: bool = True
    parameters: SerializeAsAny[CheckParameters]
    on_pass: str = Field(..., min_length=1)
    on_failure: str = Field(..., min_length=1)
    on_unresolved: str = Field(..., min_length=1)
    related_claim_types: list[AssuranceClaimType] = Field(default_factory=list)
    related_validation_types: list[str] = Field(default_factory=list)
    related_capability_ids: list[str] = Field(default_factory=list)
    related_evidence_ids: list[str] = Field(default_factory=list)
    related_limitation_categories: list[LimitationSignificance] = Field(default_factory=list)
    content_id: str = ""

    @model_validator(mode="before")
    @classmethod
    def parse_parameters(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        check_type = data.get("check_type")
        model = CHECK_PARAMETER_MODELS.get(str(check_type))
        if model is None:
            raise ValueError(f"unsupported policy check type: {check_type}")
        prepared = dict(data)
        raw_parameters = prepared.get("parameters", {})
        prepared["parameters"] = model.model_validate(raw_parameters)
        return prepared

    @field_validator("related_validation_types")
    @classmethod
    def known_related_validations(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(SUPPORTED_VALIDATION_TYPES))
        if unknown:
            raise ValueError(f"unsupported validation types: {', '.join(unknown)}")
        return value

    @model_validator(mode="after")
    def validate_parameter_type_and_identity(self) -> "PolicyCheck":
        expected_model = CHECK_PARAMETER_MODELS[self.check_type]
        if not isinstance(self.parameters, expected_model):
            raise ValueError(f"parameters do not match check type {self.check_type}")
        expected = canonical_digest("policy_check", self.deterministic_payload())
        if self.content_id and self.content_id != expected:
            raise ValueError(f"policy check content ID mismatch: {self.check_id}")
        if not self.content_id:
            object.__setattr__(self, "content_id", expected)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", serialize_as_any=True)
        data.pop("content_id", None)
        return data


class ReviewPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    policy_id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    policy_version: str = Field(..., pattern=r"^\d+(\.\d+)+$")
    policy_scope: PolicyScope
    applicable_families: list[str] = Field(..., min_length=1)
    applicable_operations: list[str] = Field(..., min_length=1)
    required_assurance_profiles: list[AssuranceProfile] = Field(..., min_length=1)
    subject_type: PolicySubjectType
    checks: list[PolicyCheck] = Field(..., min_length=1)
    decision_strategy: str = Field(default="deterministic_precedence_v1", min_length=1)
    provenance: str = Field(..., min_length=1)
    limitations: list[str] = Field(default_factory=list)
    review_notice: str = Field(..., min_length=1)
    content_id: str = ""

    @field_validator("applicable_families")
    @classmethod
    def known_families(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(SUPPORTED_POLICY_FAMILIES))
        if unknown:
            raise ValueError(f"unsupported policy families: {', '.join(unknown)}")
        return sorted(set(value))

    @field_validator("applicable_operations")
    @classmethod
    def known_operations(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(SUPPORTED_POLICY_OPERATIONS))
        if unknown:
            raise ValueError(f"unsupported policy operations: {', '.join(unknown)}")
        return sorted(set(value))

    @model_validator(mode="after")
    def validate_checks_and_identity(self) -> "ReviewPolicy":
        check_ids = [check.check_id for check in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError(f"duplicate check ids in policy {self.policy_id}")
        ordered = sorted(self.checks, key=lambda item: item.check_id)
        if self.checks != ordered:
            object.__setattr__(self, "checks", ordered)
        expected = canonical_digest("review_policy", self.deterministic_payload())
        if self.content_id and self.content_id != expected:
            raise ValueError(f"review policy content ID mismatch: {self.policy_id}")
        if not self.content_id:
            object.__setattr__(self, "content_id", expected)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", serialize_as_any=True)
        data.pop("content_id", None)
        data["checks"] = sorted(data["checks"], key=lambda item: item["check_id"])
        return data

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json", serialize_as_any=True), indent=2, sort_keys=True) + "\n"


class ReviewPolicyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    manifest_version: str = Field(default="1.0", pattern=r"^\d+(\.\d+)+$")
    generated_by: str = Field(default="intentforge")
    policies: list[ReviewPolicy] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_unique_policies(self) -> "ReviewPolicyManifest":
        policy_ids = [policy.policy_id for policy in self.policies]
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("duplicate review policy ids")
        ordered = sorted(self.policies, key=lambda item: item.policy_id)
        if self.policies != ordered:
            object.__setattr__(self, "policies", ordered)
        return self


class PolicyFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    finding_id: str
    check_id: str
    status: PolicyCheckStatus
    severity: PolicyCheckSeverity
    title: str
    summary: str
    observed_value: Any = None
    expected_value: Any = None
    claim_ids: list[str] = Field(default_factory=list)
    argument_ids: list[str] = Field(default_factory=list)
    validation_ids: list[str] = Field(default_factory=list)
    capability_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    limitation_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    content_id: str

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data.pop("finding_id", None)
        data.pop("content_id", None)
        return data


class AcceptanceCondition(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    condition_id: str
    source_check_id: str
    title: str
    description: str
    condition_type: ConditionType
    blocking: bool
    required_action: str
    related_claim_ids: list[str] = Field(default_factory=list)
    related_validation_ids: list[str] = Field(default_factory=list)
    related_limitation_ids: list[str] = Field(default_factory=list)
    content_id: str

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data.pop("condition_id", None)
        data.pop("content_id", None)
        return data


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    decision_id: str
    schema_version: str = REVIEW_SCHEMA_VERSION
    policy_id: str
    policy_version: str
    policy_content_id: str
    assurance_case_id: str
    assurance_case_content_id: str
    subject_type: PolicySubjectType
    cad_family: str
    operation: str
    assurance_profile: AssuranceProfile
    predecessor_hash_pointer: str | None = None
    decision_status: ReviewDecisionStatus
    findings: list[PolicyFinding] = Field(default_factory=list)
    conditions: list[AcceptanceCondition] = Field(default_factory=list)
    passed_check_count: int = Field(ge=0)
    failed_check_count: int = Field(ge=0)
    unresolved_check_count: int = Field(ge=0)
    not_applicable_check_count: int = Field(ge=0)
    blocking_finding_count: int = Field(ge=0)
    manual_review_finding_count: int = Field(ge=0)
    conditional_finding_count: int = Field(ge=0)
    relevant_capability_ids: list[str] = Field(default_factory=list)
    relevant_evidence_ids: list[str] = Field(default_factory=list)
    relevant_rule_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_notice: str
    provenance: str
    decision_provenance: DecisionProvenance | None = None
    content_id: str
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)
    applied_exemption_references: list[dict[str, Any]] = Field(default_factory=list)
    exemption_evaluation_content_id: str | None = None
    exemption_elevation_reason: str | None = None

    @field_validator("cad_family")
    @classmethod
    def known_family(cls, value: str) -> str:
        if value not in SUPPORTED_POLICY_FAMILIES:
            raise ValueError(f"unsupported CAD family: {value}")
        return value

    @field_validator("predecessor_hash_pointer")
    @classmethod
    def valid_predecessor(cls, value: str | None) -> str | None:
        return validate_content_address(value)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "ReviewDecision":
        finding_ids = [finding.finding_id for finding in self.findings]
        condition_ids = [condition.condition_id for condition in self.conditions]
        if len(finding_ids) != len(set(finding_ids)):
            raise ValueError("duplicate finding ids")
        if len(condition_ids) != len(set(condition_ids)):
            raise ValueError("duplicate condition ids")
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        for field_name in ("decision_id", "content_id", "runtime_metadata"):
            data.pop(field_name, None)
        if data.get("predecessor_hash_pointer") is None:
            data.pop("predecessor_hash_pointer", None)
        # Preserve Phase 24 identities for legacy decisions that predate the
        # additive provenance field.
        if data.get("decision_provenance") is None:
            data.pop("decision_provenance", None)
        else:
            provenance = self.decision_provenance
            assert provenance is not None
            data["decision_provenance"] = {
                "provenance_id": provenance.provenance_id,
                "content_id": provenance.content_id,
            }
        data["findings"] = sorted(data["findings"], key=lambda item: item["finding_id"])
        data["conditions"] = sorted(data["conditions"], key=lambda item: item["condition_id"])
        return data

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


class ReviewPolicyValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    policies_checked: int = 0
    checks_checked: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)


class ReviewDecisionValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)


def compute_policy_check_content_id(check: PolicyCheck | dict[str, Any]) -> str:
    record = check if isinstance(check, PolicyCheck) else PolicyCheck.model_validate(check)
    return canonical_digest("policy_check", record.deterministic_payload())


def compute_review_policy_content_id(policy: ReviewPolicy | dict[str, Any]) -> str:
    record = policy if isinstance(policy, ReviewPolicy) else ReviewPolicy.model_validate(policy)
    return canonical_digest("review_policy", record.deterministic_payload())


def compute_review_decision_content_id(decision: ReviewDecision | dict[str, Any]) -> str:
    record = decision if isinstance(decision, ReviewDecision) else ReviewDecision.model_validate(decision)
    return canonical_digest("review_decision_content", record.deterministic_payload())
