"""Closed registry of deterministic review-policy check evaluators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from intentforge.assurance.schema import AssuranceCase
from intentforge.knowledge.evidence_registry import load_evidence_definitions
from intentforge.knowledge.evidence_resolver import resolve_evidence
from intentforge.review.schema import (
    ArtifactIntegrityRequiredParameters,
    AssuranceProfileAllowedParameters,
    AuditPackageValidParameters,
    EditIntentPreservationRequiredParameters,
    ForbiddenClaimStatusParameters,
    LimitationCategoryParameters,
    MaximumPartialClaimCountParameters,
    MinimumAssuranceProfileParameters,
    NoCadArtifactOnRejectionParameters,
    OverallAssuranceStatusAllowedParameters,
    PolicyCheck,
    PolicyCheckStatus,
    RequiredCapabilityReferenceParameters,
    RequiredClaimPresentParameters,
    RequiredClaimStatusParameters,
    RequiredEvidenceStatusParameters,
    RequiredReviewDisclosedParameters,
    RequiredRuleReferenceParameters,
    RequiredValidationPresentParameters,
    RequiredValidationStatusParameters,
    ReproducibilityRequiredParameters,
    SafeRejectionVerifiedParameters,
    SchemaVersionSupportedParameters,
    UnsupportedBoundaryDisclosedParameters,
)


PROFILE_RANK = {"static": 0, "standard": 1, "full": 2}
FEATURE_CAPABILITY_FLAGS = {
    "wall_rounded_corners": "rounded_corners",
    "wall_edge_fillets": "edge_fillets",
    "l_inside_fillet_intent": "inside_fillet",
}


@dataclass(frozen=True)
class CheckEvaluation:
    status: PolicyCheckStatus
    observed_value: Any
    expected_value: Any
    claim_ids: list[str] = field(default_factory=list)
    argument_ids: list[str] = field(default_factory=list)
    validation_ids: list[str] = field(default_factory=list)
    capability_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    rule_ids: list[str] = field(default_factory=list)
    limitation_ids: list[str] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


CheckEvaluator = Callable[[PolicyCheck, AssuranceCase, dict[str, Any] | None], CheckEvaluation]


def _claims(case: AssuranceCase, claim_types: list[str] | None = None):
    selected = case.claims
    if claim_types is not None:
        selected = [claim for claim in selected if claim.claim_type in claim_types]
    return sorted(selected, key=lambda item: item.claim_id)


def _claim_refs(claims) -> dict[str, list[str]]:
    return {
        "claim_ids": sorted(claim.claim_id for claim in claims),
        "argument_ids": sorted({item for claim in claims for item in claim.argument_ids}),
        "validation_ids": sorted({item for claim in claims for item in claim.supporting_validation_ids}),
        "capability_ids": sorted({item for claim in claims for item in claim.capability_ids}),
        "evidence_ids": sorted({item for claim in claims for item in claim.supporting_evidence_ids}),
        "rule_ids": sorted({item for claim in claims for item in claim.rule_ids}),
        "artifact_ids": sorted({item for claim in claims for item in claim.supporting_artifact_ids}),
    }


def _validations(case: AssuranceCase, validation_types: list[str]):
    return sorted(
        [item for item in case.validation_observations if item.validation_type in validation_types],
        key=lambda item: (item.validation_type, item.validation_id),
    )


def _validation_refs(observations) -> dict[str, list[str]]:
    return {
        "validation_ids": sorted(item.validation_id for item in observations),
        "artifact_ids": sorted({artifact for item in observations for artifact in item.artifact_ids}),
        "rule_ids": sorted({rule for item in observations for rule in item.rule_ids}),
    }


def _feature_requested(case: AssuranceCase, capability_id: str) -> bool | None:
    flag_name = FEATURE_CAPABILITY_FLAGS.get(capability_id)
    if flag_name is None:
        return False
    intent = case.structured_intent or {}
    metadata = intent.get("metadata") if isinstance(intent, dict) else None
    flags = metadata.get("feature_flags") if isinstance(metadata, dict) else None
    if not isinstance(flags, dict):
        return None
    flag = flags.get(flag_name)
    if not isinstance(flag, dict):
        return None
    return flag.get("state") == "requested_by_user"


def _relevant_limitations(case: AssuranceCase, parameters: LimitationCategoryParameters):
    selected = [item for item in case.limitations if item.significance in parameters.categories]
    if parameters.capability_ids:
        selected = [
            item for item in selected
            if set(item.capability_ids).intersection(parameters.capability_ids)
        ]
    if parameters.only_when_exercised:
        relevant = []
        unresolved = []
        for item in selected:
            states = [_feature_requested(case, capability_id) for capability_id in item.capability_ids]
            if any(state is True for state in states):
                relevant.append(item)
            elif any(state is None for state in states):
                unresolved.append(item)
        return relevant, unresolved
    return selected, []


def _limitation_refs(limitations) -> dict[str, list[str]]:
    return {
        "limitation_ids": sorted(item.limitation_id for item in limitations),
        "capability_ids": sorted({capability for item in limitations for capability in item.capability_ids}),
        "rule_ids": sorted({rule for item in limitations for rule in item.rule_ids}),
    }


def _assurance_profile_allowed(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, AssuranceProfileAllowedParameters)
    passed = case.profile in params.allowed_profiles
    return CheckEvaluation("passed" if passed else "failed", case.profile, params.allowed_profiles)


def _minimum_assurance_profile(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, MinimumAssuranceProfileParameters)
    passed = PROFILE_RANK[case.profile] >= PROFILE_RANK[params.minimum_profile]
    return CheckEvaluation("passed" if passed else "failed", case.profile, params.minimum_profile)


def _overall_assurance_status_allowed(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, OverallAssuranceStatusAllowedParameters)
    passed = case.overall_assurance_status in params.allowed_statuses
    return CheckEvaluation("passed" if passed else "failed", case.overall_assurance_status, params.allowed_statuses)


def _required_claim_present(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, RequiredClaimPresentParameters)
    selected = _claims(case, params.claim_types)
    present = {claim.claim_type for claim in selected}
    missing = sorted(set(params.claim_types) - present)
    refs = _claim_refs(selected)
    return CheckEvaluation(
        "unresolved" if missing else "passed",
        {"present": sorted(present), "missing": missing},
        {"required": sorted(params.claim_types)},
        diagnostics=[f"missing claim type: {item}" for item in missing],
        **refs,
    )


def _required_claim_status(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, RequiredClaimStatusParameters)
    selected = _claims(case, params.claim_types)
    by_type = {claim.claim_type: claim for claim in selected}
    missing = sorted(set(params.claim_types) - set(by_type))
    disallowed = sorted(
        claim.claim_type for claim in selected if claim.status not in params.allowed_statuses
    )
    status: PolicyCheckStatus = "unresolved" if missing else "failed" if disallowed else "passed"
    refs = _claim_refs(selected)
    return CheckEvaluation(
        status,
        {"statuses": {kind: by_type[kind].status for kind in sorted(by_type)}, "missing": missing},
        {"required_claim_types": sorted(params.claim_types), "allowed_statuses": sorted(params.allowed_statuses)},
        diagnostics=[f"missing claim type: {item}" for item in missing]
        + [f"disallowed claim status: {item}" for item in disallowed],
        **refs,
    )


def _forbidden_claim_status(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, ForbiddenClaimStatusParameters)
    selected = [claim for claim in case.claims if claim.status in params.forbidden_statuses]
    refs = _claim_refs(selected)
    return CheckEvaluation(
        "failed" if selected else "passed",
        {"matching_claim_count": len(selected), "statuses": sorted({claim.status for claim in selected})},
        {"forbidden_statuses": sorted(params.forbidden_statuses)},
        **refs,
    )


def _maximum_partial_claim_count(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, MaximumPartialClaimCountParameters)
    selected = [claim for claim in case.claims if claim.status == "partially_supported"]
    refs = _claim_refs(selected)
    return CheckEvaluation(
        "passed" if len(selected) <= params.maximum else "failed",
        len(selected), params.maximum, **refs,
    )


def _zero_failed_claims(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    selected = [claim for claim in case.claims if claim.status == "failed"]
    return CheckEvaluation("failed" if selected else "passed", len(selected), 0, **_claim_refs(selected))


def _zero_unresolved_claims(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    selected = [claim for claim in case.claims if claim.status == "unresolved"]
    return CheckEvaluation("failed" if selected else "passed", len(selected), 0, **_claim_refs(selected))


def _required_validation_present(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, RequiredValidationPresentParameters)
    selected = _validations(case, params.validation_types)
    present = {item.validation_type for item in selected}
    missing = sorted(set(params.validation_types) - present)
    return CheckEvaluation(
        "unresolved" if missing else "passed",
        {"present": sorted(present), "missing": missing},
        {"required": sorted(params.validation_types)},
        diagnostics=[f"missing validation type: {item}" for item in missing],
        **_validation_refs(selected),
    )


def _required_validation_status(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, RequiredValidationStatusParameters)
    selected = _validations(case, params.validation_types)
    by_type = {item.validation_type: item for item in selected}
    missing = sorted(set(params.validation_types) - set(by_type))
    disallowed = sorted(
        item.validation_type for item in selected if item.status not in params.allowed_statuses
    )
    status: PolicyCheckStatus = "unresolved" if missing else "failed" if disallowed else "passed"
    return CheckEvaluation(
        status,
        {"statuses": {kind: by_type[kind].status for kind in sorted(by_type)}, "missing": missing},
        {"required_validation_types": sorted(params.validation_types), "allowed_statuses": sorted(params.allowed_statuses)},
        diagnostics=[f"missing validation type: {item}" for item in missing]
        + [f"disallowed validation status: {item}" for item in disallowed],
        **_validation_refs(selected),
    )


def _required_evidence_status(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, RequiredEvidenceStatusParameters)
    target_ids = sorted(set(params.evidence_ids or case.evidence_references))
    if not target_ids:
        return CheckEvaluation("unresolved", {"evidence_ids": []}, {"allowed_statuses": params.allowed_statuses}, diagnostics=["no evidence references supplied"])
    case_missing = sorted(set(params.evidence_ids) - set(case.evidence_references)) if params.evidence_ids else []
    definitions = [item for item in load_evidence_definitions() if item.evidence_id in target_ids]
    definition_ids = {item.evidence_id for item in definitions}
    unknown = sorted(set(target_ids) - definition_ids)
    if case_missing or unknown:
        return CheckEvaluation(
            "unresolved",
            {"case_missing": case_missing, "unknown": unknown},
            {"allowed_statuses": sorted(params.allowed_statuses)},
            evidence_ids=target_ids,
            diagnostics=[f"evidence not referenced by case: {item}" for item in case_missing]
            + [f"unknown evidence: {item}" for item in unknown],
        )
    report = resolve_evidence(definitions, runtime=False)
    statuses = {item.evidence_id: item.status for item in report.observations}
    disallowed = sorted(item for item, status in statuses.items() if status not in params.allowed_statuses)
    return CheckEvaluation(
        "failed" if disallowed else "passed",
        {"statuses": {item: statuses[item] for item in sorted(statuses)}},
        {"allowed_statuses": sorted(params.allowed_statuses)},
        evidence_ids=target_ids,
        diagnostics=[f"disallowed evidence status: {item}" for item in disallowed],
    )


def _required_capability_reference(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, RequiredCapabilityReferenceParameters)
    missing = sorted(set(params.capability_ids) - set(case.capability_references))
    present = sorted(set(params.capability_ids).intersection(case.capability_references))
    return CheckEvaluation(
        "unresolved" if missing else "passed",
        {"present": present, "missing": missing},
        {"required": sorted(params.capability_ids)},
        capability_ids=present,
        diagnostics=[f"missing capability reference: {item}" for item in missing],
    )


def _required_rule_reference(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, RequiredRuleReferenceParameters)
    available = {str(item.get("rule_id")) for item in case.rule_references}
    missing = sorted(set(params.rule_ids) - available)
    present = sorted(set(params.rule_ids).intersection(available))
    return CheckEvaluation(
        "unresolved" if missing else "passed",
        {"present": present, "missing": missing},
        {"required": sorted(params.rule_ids)},
        rule_ids=present,
        diagnostics=[f"missing rule reference: {item}" for item in missing],
    )


def _artifact_integrity_required(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, ArtifactIntegrityRequiredParameters)
    artifacts = sorted(case.artifact_records, key=lambda item: item.artifact_id)
    claims = _claims(case, ["artifact_integrity_verified"])
    missing_artifacts = params.require_artifacts and not artifacts
    unhashed = [item.artifact_id for item in artifacts if not item.content_hash]
    bad_status = [item.artifact_id for item in artifacts if item.validation_status != "verified"]
    missing_claim = params.require_integrity_claim and not any(claim.status == "supported" for claim in claims)
    unresolved = bool(missing_artifacts or missing_claim)
    failed = bool((params.require_all_hashed and unhashed) or bad_status)
    status: PolicyCheckStatus = "unresolved" if unresolved else "failed" if failed else "passed"
    refs = _claim_refs(claims)
    refs["artifact_ids"] = sorted({*refs["artifact_ids"], *(item.artifact_id for item in artifacts)})
    return CheckEvaluation(
        status,
        {
            "artifact_count": len(artifacts),
            "content_hashes": {item.artifact_id: item.content_hash for item in artifacts},
            "unhashed": sorted(unhashed),
            "invalid_status": sorted(bad_status),
            "integrity_claim": bool(claims),
        },
        {"artifacts_required": params.require_artifacts, "all_hashed": params.require_all_hashed, "integrity_claim_required": params.require_integrity_claim},
        diagnostics=([] if artifacts else ["no artifact records"])
        + [f"unhashed artifact: {item}" for item in sorted(unhashed)]
        + [f"artifact integrity not verified: {item}" for item in sorted(bad_status)]
        + (["artifact integrity claim missing"] if missing_claim else []),
        **refs,
    )


def _audit_package_valid(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, AuditPackageValidParameters)
    if package_result is None:
        return CheckEvaluation("unresolved" if params.require_package else "not_checked", None, {"passed": True}, diagnostics=["audit package result not supplied"])
    passed = bool(package_result.get("passed", package_result.get("validation", {}).get("passed", False)))
    return CheckEvaluation(
        "passed" if passed else "failed",
        {"passed": passed, "package_id": package_result.get("package_id") or package_result.get("validation", {}).get("package_id")},
        {"passed": True},
        diagnostics=list(package_result.get("errors", package_result.get("validation", {}).get("errors", [])) or []),
    )


def _reproducibility_required(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, ReproducibilityRequiredParameters)
    deterministic = case.reproducibility_metadata.get("deterministic") is True
    package_supplied = package_result is not None
    package_passed = bool(package_result and package_result.get("passed", package_result.get("validation", {}).get("passed", False)))
    if params.require_valid_audit_package and not package_supplied:
        status: PolicyCheckStatus = "unresolved"
    elif (params.require_deterministic_metadata and not deterministic) or (params.require_valid_audit_package and not package_passed):
        status = "failed"
    else:
        status = "passed"
    return CheckEvaluation(
        status,
        {"deterministic_metadata": deterministic, "audit_package_supplied": package_supplied, "audit_package_valid": package_passed},
        {"deterministic_metadata": params.require_deterministic_metadata, "valid_audit_package": params.require_valid_audit_package},
        diagnostics=["valid audit package result not supplied"] if status == "unresolved" else [],
    )


def _limitation_category_allowed(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, LimitationCategoryParameters)
    selected = case.limitations
    if params.capability_ids:
        selected = [item for item in selected if set(item.capability_ids).intersection(params.capability_ids)]
    disallowed = [item for item in selected if item.significance not in params.categories]
    return CheckEvaluation(
        "failed" if disallowed else "passed",
        {"disallowed_categories": sorted({item.significance for item in disallowed})},
        {"allowed_categories": sorted(params.categories)},
        **_limitation_refs(disallowed),
    )


def _limitation_category_forbidden(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, LimitationCategoryParameters)
    selected, unresolved = _relevant_limitations(case, params)
    if unresolved:
        return CheckEvaluation("unresolved", {"unresolved_count": len(unresolved)}, {"forbidden_categories": sorted(params.categories)}, **_limitation_refs(unresolved))
    return CheckEvaluation(
        "failed" if selected else "passed",
        {"matching_count": len(selected)},
        {"forbidden_categories": sorted(params.categories)},
        **_limitation_refs(selected),
    )


def _limitation_requires_manual_review(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, LimitationCategoryParameters)
    selected, unresolved = _relevant_limitations(case, params)
    if unresolved and not selected:
        return CheckEvaluation("unresolved", {"unresolved_count": len(unresolved)}, {"manual_review_categories": sorted(params.categories)}, **_limitation_refs(unresolved))
    if not selected:
        return CheckEvaluation("not_applicable", {"matching_count": 0}, {"manual_review_categories": sorted(params.categories)})
    return CheckEvaluation(
        "failed",
        {"matching_count": len(selected), "limitations": [item.title for item in selected]},
        {"manual_review_categories": sorted(params.categories)},
        **_limitation_refs(selected),
    )


def _unsupported_boundary_disclosed(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, UnsupportedBoundaryDisclosedParameters)
    selected = [item for item in case.limitations if item.significance == "unsupported_boundary"]
    return CheckEvaluation(
        "passed" if len(selected) >= params.minimum_count else "failed",
        len(selected), {"minimum_count": params.minimum_count}, **_limitation_refs(selected),
    )


def _safe_rejection_verified(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, SafeRejectionVerifiedParameters)
    claims = _claims(case, ["unsupported_behavior_rejected"])
    supported_claim = any(claim.status == "supported" for claim in claims)
    error = case.input_request.get("error")
    structured_error = isinstance(error, dict) and bool(error.get("error_type")) and bool(error.get("message"))
    boundaries = [item for item in case.limitations if item.significance == "unsupported_boundary"]
    definitions = {item.evidence_id: item for item in load_evidence_definitions()}
    boundary_evidence = [
        evidence_id for evidence_id in case.evidence_references
        if evidence_id in definitions and definitions[evidence_id].role == "boundary"
    ]
    missing = []
    if not supported_claim: missing.append("supported rejection claim")
    if params.require_structured_error and not structured_error: missing.append("structured rejection error")
    if params.require_boundary and not boundaries: missing.append("unsupported boundary")
    if params.require_rejection_evidence and not boundary_evidence: missing.append("boundary evidence")
    status: PolicyCheckStatus = "unresolved" if missing else "passed"
    refs = _claim_refs(claims)
    refs["limitation_ids"] = sorted(item.limitation_id for item in boundaries)
    refs["capability_ids"] = sorted({*refs["capability_ids"], *(cap for item in boundaries for cap in item.capability_ids)})
    refs["evidence_ids"] = sorted({*refs["evidence_ids"], *boundary_evidence})
    return CheckEvaluation(
        status,
        {"supported_rejection_claim": supported_claim, "structured_error": structured_error, "boundary_count": len(boundaries), "boundary_evidence_count": len(boundary_evidence)},
        {"all_required": True},
        diagnostics=[f"missing {item}" for item in missing],
        **refs,
    )


def _no_cad_artifact_on_rejection(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, NoCadArtifactOnRejectionParameters)
    artifacts = sorted(case.artifact_records, key=lambda item: item.artifact_id)
    geometry_claims = _claims(case, ["geometry_generated", "geometry_valid"])
    bad_claims = [claim for claim in geometry_claims if claim.status == "supported"] if params.forbid_geometry_claims else []
    failed = bool(artifacts or bad_claims)
    refs = _claim_refs(bad_claims)
    refs["artifact_ids"] = sorted({*refs["artifact_ids"], *(item.artifact_id for item in artifacts)})
    return CheckEvaluation(
        "failed" if failed else "passed",
        {"artifact_count": len(artifacts), "successful_geometry_claim_count": len(bad_claims)},
        {"artifact_count": 0, "successful_geometry_claim_count": 0},
        **refs,
    )


def _edit_intent_preservation_required(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, EditIntentPreservationRequiredParameters)
    claims = _claims(case, ["requested_edit_preserved_intent"])
    supported = any(claim.status == "supported" for claim in claims)
    trace = case.input_request.get("edit_trace")
    changed = trace.get("changed_parameters") if isinstance(trace, dict) else None
    preserved = trace.get("preserved_parameters") if isinstance(trace, dict) else None
    missing = []
    failed = bool(claims and not supported)
    if not claims: missing.append("intent-preservation claim")
    if params.require_parent_run_id and not case.parent_run_id: missing.append("parent run ID")
    if params.require_change_trace and not changed: missing.append("changed-parameter trace")
    if params.require_preservation_trace and not preserved: missing.append("preserved-parameter trace")
    status: PolicyCheckStatus = "failed" if failed else "unresolved" if missing else "passed"
    return CheckEvaluation(
        status,
        {"claim_supported": supported, "parent_run_id_present": bool(case.parent_run_id), "changed_parameter_count": len(changed or []), "preserved_parameter_count": len(preserved or [])},
        {"preservation_claim": True, "parent_run_id": params.require_parent_run_id, "change_trace": params.require_change_trace, "preservation_trace": params.require_preservation_trace},
        diagnostics=[f"missing {item}" for item in missing],
        **_claim_refs(claims),
    )


def _required_review_disclosed(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, RequiredReviewDisclosedParameters)
    return CheckEvaluation(
        "passed" if len(case.review_requirements) >= params.minimum_count else "failed",
        len(case.review_requirements), {"minimum_count": params.minimum_count},
    )


def _schema_version_supported(check: PolicyCheck, case: AssuranceCase, package_result) -> CheckEvaluation:
    params = check.parameters
    assert isinstance(params, SchemaVersionSupportedParameters)
    return CheckEvaluation(
        "passed" if case.schema_version in params.supported_versions else "failed",
        case.schema_version, params.supported_versions,
    )


CHECK_EVALUATORS: dict[str, CheckEvaluator] = {
    "assurance_profile_allowed": _assurance_profile_allowed,
    "overall_assurance_status_allowed": _overall_assurance_status_allowed,
    "required_claim_present": _required_claim_present,
    "required_claim_status": _required_claim_status,
    "forbidden_claim_status": _forbidden_claim_status,
    "maximum_partial_claim_count": _maximum_partial_claim_count,
    "zero_failed_claims": _zero_failed_claims,
    "zero_unresolved_claims": _zero_unresolved_claims,
    "required_validation_present": _required_validation_present,
    "required_validation_status": _required_validation_status,
    "required_evidence_status": _required_evidence_status,
    "required_capability_reference": _required_capability_reference,
    "required_rule_reference": _required_rule_reference,
    "artifact_integrity_required": _artifact_integrity_required,
    "audit_package_valid": _audit_package_valid,
    "reproducibility_required": _reproducibility_required,
    "limitation_category_allowed": _limitation_category_allowed,
    "limitation_category_forbidden": _limitation_category_forbidden,
    "limitation_requires_manual_review": _limitation_requires_manual_review,
    "unsupported_boundary_disclosed": _unsupported_boundary_disclosed,
    "safe_rejection_verified": _safe_rejection_verified,
    "no_cad_artifact_on_rejection": _no_cad_artifact_on_rejection,
    "edit_intent_preservation_required": _edit_intent_preservation_required,
    "required_review_disclosed": _required_review_disclosed,
    "minimum_assurance_profile": _minimum_assurance_profile,
    "schema_version_supported": _schema_version_supported,
}


def evaluate_policy_check(
    check: PolicyCheck,
    case: AssuranceCase,
    package_result: dict[str, Any] | None = None,
) -> CheckEvaluation:
    """Evaluate one registered check without manifest-selected code execution."""

    evaluator = CHECK_EVALUATORS.get(check.check_type)
    if evaluator is None:
        raise ValueError(f"unregistered policy check type: {check.check_type}")
    return evaluator(check, case, package_result)
