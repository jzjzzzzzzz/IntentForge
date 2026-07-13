"""Deterministic review-policy evaluation over existing assurance records."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from intentforge.assurance.schema import AssuranceCase, canonical_digest
from intentforge.assurance.validator import validate_assurance_case
from intentforge.review.checks import CheckEvaluation, evaluate_policy_check
from intentforge.review.exemption_engine import apply_exemptions_to_decision
from intentforge.review.exemption_schema import ExemptionManifest
from intentforge.review.provenance import (
    ReviewEvaluationResources,
    build_decision_provenance,
    collect_review_evaluation_resources,
)
from intentforge.review.schema import (
    AcceptanceCondition,
    PolicyCheck,
    PolicyFinding,
    ReviewDecision,
    ReviewDecisionStatus,
    ReviewPolicy,
)


class ReviewEvaluationError(ValueError):
    """Structured input or policy-scope error raised before check evaluation."""

    def __init__(self, message: str, *, error_code: str = "invalid_review_input"):
        super().__init__(message)
        self.error_code = error_code


def determine_subject_type(case: AssuranceCase) -> str:
    if any(claim.claim_type == "unsupported_behavior_rejected" for claim in case.claims):
        return "safe_rejection"
    if case.operation.startswith("edit_"):
        return "edit_result"
    return "design_result"


def _finding(check: PolicyCheck, evaluation: CheckEvaluation) -> PolicyFinding:
    summary = (
        check.on_pass if evaluation.status == "passed"
        else check.on_failure if evaluation.status == "failed"
        else check.on_unresolved if evaluation.status in {"unresolved", "not_checked"}
        else "This check does not apply to the reviewed assurance case."
    )
    payload = {
        "check_id": check.check_id,
        "status": evaluation.status,
        "severity": check.severity,
        "title": check.title,
        "summary": summary,
        "observed_value": evaluation.observed_value,
        "expected_value": evaluation.expected_value,
        "claim_ids": sorted(set(evaluation.claim_ids)),
        "argument_ids": sorted(set(evaluation.argument_ids)),
        "validation_ids": sorted(set(evaluation.validation_ids)),
        "capability_ids": sorted(set(evaluation.capability_ids)),
        "evidence_ids": sorted(set(evaluation.evidence_ids)),
        "rule_ids": sorted(set(evaluation.rule_ids)),
        "limitation_ids": sorted(set(evaluation.limitation_ids)),
        "artifact_ids": sorted(set(evaluation.artifact_ids)),
        "diagnostics": sorted(set(evaluation.diagnostics)),
    }
    content_id = canonical_digest("policy_finding_content", payload)
    return PolicyFinding(
        finding_id=canonical_digest("policy_finding", {"content_id": content_id}),
        content_id=content_id,
        **payload,
    )


def _condition_type(check: PolicyCheck, finding: PolicyFinding) -> str:
    if check.check_type == "artifact_integrity_required":
        return "artifact_integrity_required"
    if check.check_type in {"reproducibility_required", "audit_package_valid"}:
        return "reproducibility_check_required"
    if check.check_type.startswith("limitation_"):
        return "external_review_required" if check.severity == "manual_review" else "limitation_acknowledgement_required"
    if check.check_type in {"safe_rejection_verified", "no_cad_artifact_on_rejection", "unsupported_boundary_disclosed"}:
        return "unsupported_scope_correction_required"
    if check.check_type in {"required_claim_present", "required_claim_status", "edit_intent_preservation_required"}:
        return "intent_clarification_required"
    return "additional_validation_required"


def _condition(check: PolicyCheck, finding: PolicyFinding) -> AcceptanceCondition | None:
    if finding.status not in {"failed", "unresolved", "not_checked"}:
        return None
    if check.severity not in {"conditional", "manual_review", "blocking"}:
        return None
    payload = {
        "source_check_id": check.check_id,
        "title": check.title,
        "description": finding.summary,
        "condition_type": _condition_type(check, finding),
        "blocking": check.severity == "blocking",
        "required_action": check.on_unresolved if finding.status in {"unresolved", "not_checked"} else check.on_failure,
        "related_claim_ids": finding.claim_ids,
        "related_validation_ids": finding.validation_ids,
        "related_limitation_ids": finding.limitation_ids,
    }
    content_id = canonical_digest("acceptance_condition_content", payload)
    return AcceptanceCondition(
        condition_id=canonical_digest("acceptance_condition", {"content_id": content_id}),
        content_id=content_id,
        **payload,
    )


def _decision_status(policy: ReviewPolicy, findings: list[PolicyFinding]) -> ReviewDecisionStatus:
    checks = {check.check_id: check for check in policy.checks}
    required_blocking_unresolved = any(
        finding.status in {"unresolved", "not_checked"}
        and finding.severity == "blocking"
        and checks[finding.check_id].required
        for finding in findings
    )
    if required_blocking_unresolved:
        return "unresolved"
    if any(finding.status == "failed" and finding.severity == "blocking" for finding in findings):
        return "rejected_by_policy"
    if any(
        finding.status in {"failed", "unresolved", "not_checked"}
        and finding.severity == "manual_review"
        for finding in findings
    ):
        return "manual_review_required"
    if any(
        finding.status in {"failed", "unresolved", "not_checked"}
        and finding.severity == "conditional"
        for finding in findings
    ):
        return "accepted_with_conditions"
    # ``accepted_with_exemption`` is produced exclusively by
    # ``apply_exemptions_to_decision`` once a manifest matches a blocking
    # finding. The deterministic precedence contract here never emits it
    # directly so the close-rejection path remains explicit and auditable.
    return "accepted_within_declared_scope"


def evaluate_assurance_case(
    policy: ReviewPolicy | dict[str, Any],
    assurance_case: AssuranceCase | dict[str, Any],
    package_result: dict[str, Any] | None = None,
    *,
    runtime_metadata: dict[str, Any] | None = None,
    resources: ReviewEvaluationResources | None = None,
    exemption_manifests: Sequence[ExemptionManifest] | None = None,
) -> ReviewDecision:
    """Evaluate a validated assurance case using only registered deterministic checks.

    When ``exemption_manifests`` is non-empty, the decision is post-processed
    through ``apply_exemptions_to_decision`` so that any matching declaration
    can deterministically elevate ``rejected_by_policy`` to the new
    ``accepted_with_exemption`` status. The exemption manifests themselves are
    returned to the caller through the ``applied_exemption_references`` field.
    """

    record = assurance_case if isinstance(assurance_case, AssuranceCase) else AssuranceCase.model_validate(assurance_case)
    selected_policy = policy if isinstance(policy, ReviewPolicy) else ReviewPolicy.model_validate(policy)
    active_evidence_ids = set(record.evidence_references)
    for policy_check in selected_policy.checks:
        active_evidence_ids.update(policy_check.related_evidence_ids)
        parameter_evidence = getattr(policy_check.parameters, "evidence_ids", [])
        if isinstance(parameter_evidence, list):
            active_evidence_ids.update(parameter_evidence)
    evaluation_resources = resources or collect_review_evaluation_resources(
        active_evidence_ids=active_evidence_ids
    )
    assurance_validation = validate_assurance_case(
        record,
        capability_ids={
            str(item.get("capability_id"))
            for item in evaluation_resources.capability_manifest.get("capabilities", [])
        },
        evidence_ids={str(item.get("evidence_id")) for item in evaluation_resources.evidence_definitions},
        rule_ids={str(item.get("id")) for item in evaluation_resources.rules},
    )
    if not assurance_validation.passed:
        raise ReviewEvaluationError(
            "assurance case is invalid: " + "; ".join(assurance_validation.errors),
            error_code="invalid_assurance_case",
        )
    subject_type = determine_subject_type(record)
    if record.cad_family not in selected_policy.applicable_families:
        raise ReviewEvaluationError(
            f"policy {selected_policy.policy_id} does not apply to family {record.cad_family}",
            error_code="policy_family_mismatch",
        )
    if record.operation not in selected_policy.applicable_operations:
        raise ReviewEvaluationError(
            f"policy {selected_policy.policy_id} does not apply to operation {record.operation}",
            error_code="policy_operation_mismatch",
        )
    if subject_type != selected_policy.subject_type:
        raise ReviewEvaluationError(
            f"policy {selected_policy.policy_id} expects {selected_policy.subject_type}, not {subject_type}",
            error_code="policy_subject_mismatch",
        )

    findings: list[PolicyFinding] = []
    conditions: list[AcceptanceCondition] = []
    check_context = evaluation_resources.check_context(package_result)
    for check in sorted(selected_policy.checks, key=lambda item: item.check_id):
        finding = _finding(check, evaluate_policy_check(check, record, check_context))
        findings.append(finding)
        condition = _condition(check, finding)
        if condition is not None:
            conditions.append(condition)
    findings.sort(key=lambda item: item.finding_id)
    conditions.sort(key=lambda item: item.condition_id)
    status = _decision_status(selected_policy, findings)
    relevant_capabilities = sorted({*record.capability_references, *(item for finding in findings for item in finding.capability_ids)})
    relevant_evidence = sorted({*record.evidence_references, *(item for finding in findings for item in finding.evidence_ids)})
    relevant_rules = sorted({*(str(item.get("rule_id")) for item in record.rule_references), *(item for finding in findings for item in finding.rule_ids)})
    decision_data = {
        "decision_id": "pending",
        "policy_id": selected_policy.policy_id,
        "policy_version": selected_policy.policy_version,
        "policy_content_id": selected_policy.content_id,
        "assurance_case_id": record.assurance_case_id,
        "assurance_case_content_id": record.content_id,
        "subject_type": subject_type,
        "cad_family": record.cad_family,
        "operation": record.operation,
        "assurance_profile": record.profile,
        "predecessor_hash_pointer": record.predecessor_hash_pointer,
        "decision_status": status,
        "findings": findings,
        "conditions": conditions,
        "passed_check_count": sum(item.status == "passed" for item in findings),
        "failed_check_count": sum(item.status == "failed" for item in findings),
        "unresolved_check_count": sum(item.status in {"unresolved", "not_checked"} for item in findings),
        "not_applicable_check_count": sum(item.status == "not_applicable" for item in findings),
        "blocking_finding_count": sum(item.status in {"failed", "unresolved", "not_checked"} and item.severity == "blocking" for item in findings),
        "manual_review_finding_count": sum(item.status in {"failed", "unresolved", "not_checked"} and item.severity == "manual_review" for item in findings),
        "conditional_finding_count": sum(item.status in {"failed", "unresolved", "not_checked"} and item.severity == "conditional" for item in findings),
        "relevant_capability_ids": relevant_capabilities,
        "relevant_evidence_ids": relevant_evidence,
        "relevant_rule_ids": relevant_rules,
        "limitations": sorted({*selected_policy.limitations, *(item.description for item in record.limitations)}),
        "review_notice": selected_policy.review_notice,
        "provenance": f"policy:{selected_policy.policy_id}@{selected_policy.policy_version}",
        "decision_provenance": None,
        "content_id": "pending",
        "runtime_metadata": runtime_metadata or {},
    }
    core_decision = ReviewDecision.model_validate(decision_data)
    decision_core_content_id = canonical_digest(
        "review_decision_core_content", core_decision.deterministic_payload()
    )
    provenance = build_decision_provenance(
        policy=selected_policy,
        assurance_case=record,
        subject_type=subject_type,
        package_result=package_result,
        resources=evaluation_resources,
        findings=findings,
        conditions=conditions,
        decision_status=status,
        decision_core_content_id=decision_core_content_id,
        runtime_metadata=runtime_metadata,
    )
    provisional = core_decision.model_copy(update={"decision_provenance": provenance})
    content_id = canonical_digest("review_decision_content", provisional.deterministic_payload())
    final_decision = provisional.model_copy(update={
        "decision_id": canonical_digest("review_decision", {"content_id": content_id}),
        "content_id": content_id,
    })
    if exemption_manifests:
        package_mapping: Mapping[str, Any] | None = package_result if isinstance(package_result, Mapping) else None
        elevated = apply_exemptions_to_decision(
            final_decision,
            list(exemption_manifests),
            package_result=package_mapping,
        )
        return elevated
    return final_decision
