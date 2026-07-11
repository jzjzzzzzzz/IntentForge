"""Semantic validation for review policies and deterministic decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from intentforge.assurance.schema import AssuranceCase, canonical_digest
from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.evidence_registry import load_evidence_definitions
from intentforge.knowledge.rules import RuleRegistry
from intentforge.review.checks import CHECK_EVALUATORS
from intentforge.review.policies import ReviewPolicyError, load_review_policy_manifest
from intentforge.review.schema import (
    LimitationCategoryParameters,
    RequiredCapabilityReferenceParameters,
    RequiredEvidenceStatusParameters,
    RequiredRuleReferenceParameters,
    ReviewDecision,
    ReviewDecisionValidationResult,
    ReviewPolicy,
    ReviewPolicyManifest,
    ReviewPolicyValidationResult,
    SUPPORTED_CHECK_TYPES,
)


RUNTIME_CHECK_TYPES = {
    "required_validation_present",
    "required_validation_status",
    "artifact_integrity_required",
    "audit_package_valid",
    "reproducibility_required",
}


def _known_references() -> tuple[set[str], set[str], set[str]]:
    capabilities = {item.capability_id for item in load_capability_manifest().capabilities}
    evidence = {item.evidence_id for item in load_evidence_definitions()}
    rules = {item.id for item in RuleRegistry.load().rules}
    return capabilities, evidence, rules


def _parameter_references(policy: ReviewPolicy) -> tuple[set[str], set[str], set[str]]:
    capabilities: set[str] = set()
    evidence: set[str] = set()
    rules: set[str] = set()
    for check in policy.checks:
        parameters = check.parameters
        if isinstance(parameters, (RequiredCapabilityReferenceParameters, LimitationCategoryParameters)):
            capabilities.update(parameters.capability_ids)
        if isinstance(parameters, RequiredEvidenceStatusParameters):
            evidence.update(parameters.evidence_ids)
        if isinstance(parameters, RequiredRuleReferenceParameters):
            rules.update(parameters.rule_ids)
    return capabilities, evidence, rules


def validate_review_policy(
    policy: ReviewPolicy | dict[str, Any],
    *,
    known_capability_ids: set[str] | None = None,
    known_evidence_ids: set[str] | None = None,
    known_rule_ids: set[str] | None = None,
) -> ReviewPolicyValidationResult:
    try:
        record = policy if isinstance(policy, ReviewPolicy) else ReviewPolicy.model_validate(policy)
    except (ValidationError, ValueError) as exc:
        return ReviewPolicyValidationResult(
            passed=False, errors=[f"invalid review policy schema: {exc}"],
            metrics={"invalid_policy_count": 1},
        )
    errors: list[str] = []
    warnings: list[str] = []
    live_capabilities: set[str] = set()
    live_evidence: set[str] = set()
    live_rules: set[str] = set()
    if known_capability_ids is None or known_evidence_ids is None or known_rule_ids is None:
        live_capabilities, live_evidence, live_rules = _known_references()
    known_capabilities = known_capability_ids if known_capability_ids is not None else live_capabilities
    known_evidence = known_evidence_ids if known_evidence_ids is not None else live_evidence
    known_rules = known_rule_ids if known_rule_ids is not None else live_rules
    parameter_capabilities, parameter_evidence, parameter_rules = _parameter_references(record)
    referenced_capabilities = {
        item for check in record.checks for item in check.related_capability_ids
    }.union(parameter_capabilities)
    referenced_evidence = {
        item for check in record.checks for item in check.related_evidence_ids
    }.union(parameter_evidence)
    referenced_rules = parameter_rules
    unknown_capabilities = sorted(referenced_capabilities - known_capabilities)
    unknown_evidence = sorted(referenced_evidence - known_evidence)
    unknown_rules = sorted(referenced_rules - known_rules)
    if unknown_capabilities:
        errors.append("unknown capability references: " + ", ".join(unknown_capabilities))
    if unknown_evidence:
        errors.append("unknown evidence references: " + ", ".join(unknown_evidence))
    if unknown_rules:
        errors.append("unknown rule references: " + ", ".join(unknown_rules))
    unregistered = sorted({check.check_type for check in record.checks} - set(CHECK_EVALUATORS))
    if unregistered:
        errors.append("unregistered check types: " + ", ".join(unregistered))
    if any(check.check_type not in SUPPORTED_CHECK_TYPES for check in record.checks):
        errors.append("policy contains unsupported check types")
    if record.subject_type == "safe_rejection":
        forbidden = sorted({check.check_type for check in record.checks}.intersection({
            "artifact_integrity_required", "audit_package_valid", "reproducibility_required",
        }))
        if forbidden:
            errors.append("safe-rejection policy cannot require CAD artifacts or reproducibility: " + ", ".join(forbidden))
    if record.required_assurance_profiles == ["static"]:
        runtime_checks = sorted({check.check_type for check in record.checks}.intersection(RUNTIME_CHECK_TYPES))
        if runtime_checks:
            errors.append("static policy cannot require runtime CAD checks: " + ", ".join(runtime_checks))
    if record.policy_scope == "assurance_case_and_audit_package" and not any(
        check.check_type == "audit_package_valid" for check in record.checks
    ):
        errors.append("audit-package policy scope requires audit_package_valid check")
    if record.policy_id == "intentforge_full_design_review_v1" and "full" not in record.required_assurance_profiles:
        errors.append("full design review policy must require the full assurance profile")
    normalized_checks = [
        json.dumps(
            {"check_type": check.check_type, "parameters": check.parameters.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        )
        for check in record.checks
    ]
    duplicate_normalized = len(normalized_checks) - len(set(normalized_checks))
    if duplicate_normalized:
        errors.append(f"duplicate normalized policy checks: {duplicate_normalized}")
    content_mismatch = 0
    for check in record.checks:
        expected = canonical_digest("policy_check", check.deterministic_payload())
        if check.content_id != expected:
            content_mismatch += 1
            errors.append(f"policy check content ID mismatch: {check.check_id}")
    expected_policy_content = canonical_digest("review_policy", record.deterministic_payload())
    if record.content_id != expected_policy_content:
        content_mismatch += 1
        errors.append("review policy content ID mismatch")
    metrics = {
        "invalid_policy_count": int(bool(errors)),
        "duplicate_check_id_count": len(record.checks) - len({item.check_id for item in record.checks}),
        "duplicate_normalized_check_count": duplicate_normalized,
        "unknown_claim_reference_count": 0,
        "unknown_validation_reference_count": 0,
        "unknown_capability_reference_count": len(unknown_capabilities),
        "unknown_evidence_reference_count": len(unknown_evidence),
        "unknown_rule_reference_count": len(unknown_rules),
        "unregistered_check_type_count": len(unregistered),
        "policy_content_id_mismatch_count": content_mismatch,
    }
    return ReviewPolicyValidationResult(
        passed=not errors,
        policies_checked=1,
        checks_checked=len(record.checks),
        errors=errors,
        warnings=warnings,
        metrics=metrics,
    )


def _raw_duplicate_policy_count(path: str | Path | None) -> int:
    if path is None:
        return 0
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return 0
    policies = raw.get("policies", []) if isinstance(raw, dict) else []
    ids = [item.get("policy_id") for item in policies if isinstance(item, dict)]
    return len(ids) - len(set(ids))


def validate_review_policy_manifest(
    manifest: ReviewPolicyManifest | dict[str, Any] | None = None,
    *,
    path: str | Path | None = None,
) -> ReviewPolicyValidationResult:
    duplicate_policy_count = _raw_duplicate_policy_count(path)
    try:
        if manifest is None:
            record = load_review_policy_manifest(path)
        else:
            record = manifest if isinstance(manifest, ReviewPolicyManifest) else ReviewPolicyManifest.model_validate(manifest)
    except (ReviewPolicyError, ValidationError, ValueError) as exc:
        return ReviewPolicyValidationResult(
            passed=False,
            errors=[f"invalid review policy manifest: {exc}"],
            metrics={"duplicate_policy_id_count": duplicate_policy_count, "invalid_policy_count": 1},
        )
    errors: list[str] = []
    warnings: list[str] = []
    aggregate: dict[str, int] = {
        "duplicate_policy_id_count": duplicate_policy_count,
        "duplicate_check_id_count": 0,
        "duplicate_normalized_check_count": 0,
        "unknown_claim_reference_count": 0,
        "unknown_validation_reference_count": 0,
        "unknown_capability_reference_count": 0,
        "unknown_evidence_reference_count": 0,
        "unknown_rule_reference_count": 0,
        "unregistered_check_type_count": 0,
        "policy_content_id_mismatch_count": 0,
        "invalid_policy_count": 0,
    }
    for policy in record.policies:
        result = validate_review_policy(policy)
        errors.extend(f"{policy.policy_id}: {error}" for error in result.errors)
        warnings.extend(f"{policy.policy_id}: {warning}" for warning in result.warnings)
        for key in aggregate:
            aggregate[key] += int(result.metrics.get(key, 0))
    return ReviewPolicyValidationResult(
        passed=not errors,
        policies_checked=len(record.policies),
        checks_checked=sum(len(policy.checks) for policy in record.policies),
        errors=errors,
        warnings=warnings,
        metrics=aggregate,
    )


def _expected_decision_status(decision: ReviewDecision, policy: ReviewPolicy) -> str:
    checks = {check.check_id: check for check in policy.checks}
    if any(
        finding.status in {"unresolved", "not_checked"}
        and finding.severity == "blocking"
        and checks.get(finding.check_id) is not None
        and checks[finding.check_id].required
        for finding in decision.findings
    ):
        return "unresolved"
    if any(finding.status == "failed" and finding.severity == "blocking" for finding in decision.findings):
        return "rejected_by_policy"
    if any(
        finding.status in {"failed", "unresolved", "not_checked"}
        and finding.severity == "manual_review"
        for finding in decision.findings
    ):
        return "manual_review_required"
    if any(
        finding.status in {"failed", "unresolved", "not_checked"}
        and finding.severity == "conditional"
        for finding in decision.findings
    ):
        return "accepted_with_conditions"
    return "accepted_within_declared_scope"


def validate_review_decision(
    decision: ReviewDecision | dict[str, Any],
    *,
    policy: ReviewPolicy | None = None,
    assurance_case: AssuranceCase | None = None,
    known_capability_ids: set[str] | None = None,
    known_evidence_ids: set[str] | None = None,
    known_rule_ids: set[str] | None = None,
) -> ReviewDecisionValidationResult:
    try:
        record = decision if isinstance(decision, ReviewDecision) else ReviewDecision.model_validate(decision)
    except (ValidationError, ValueError) as exc:
        return ReviewDecisionValidationResult(passed=False, errors=[f"invalid review decision schema: {exc}"])
    errors: list[str] = []
    if policy is None:
        try:
            from intentforge.review.policies import get_review_policy
            policy = get_review_policy(record.policy_id)
        except ReviewPolicyError as exc:
            errors.append(str(exc))
    if policy is not None:
        if record.policy_id != policy.policy_id: errors.append("policy ID mismatch")
        if record.policy_version != policy.policy_version: errors.append("policy version mismatch")
        if record.policy_content_id != policy.content_id: errors.append("policy content ID mismatch")
        expected_check_ids = {check.check_id for check in policy.checks}
        actual_check_ids = {finding.check_id for finding in record.findings}
        if actual_check_ids != expected_check_ids:
            errors.append("decision finding checks do not match policy checks")
        expected_status = _expected_decision_status(record, policy)
        if record.decision_status != expected_status:
            errors.append("review decision status does not match deterministic precedence")
    live_capabilities: set[str] = set()
    live_evidence: set[str] = set()
    live_rules: set[str] = set()
    if known_capability_ids is None or known_evidence_ids is None or known_rule_ids is None:
        live_capabilities, live_evidence, live_rules = _known_references()
    known_capabilities = known_capability_ids if known_capability_ids is not None else live_capabilities
    known_evidence = known_evidence_ids if known_evidence_ids is not None else live_evidence
    known_rules = known_rule_ids if known_rule_ids is not None else live_rules
    unknown_capabilities = sorted(set(record.relevant_capability_ids) - known_capabilities)
    unknown_evidence = sorted(set(record.relevant_evidence_ids) - known_evidence)
    unknown_rules = sorted(set(record.relevant_rule_ids) - known_rules)
    if unknown_capabilities: errors.append("unknown capability references: " + ", ".join(unknown_capabilities))
    if unknown_evidence: errors.append("unknown evidence references: " + ", ".join(unknown_evidence))
    if unknown_rules: errors.append("unknown rule references: " + ", ".join(unknown_rules))
    finding_mismatches = 0
    for finding in record.findings:
        expected_content = canonical_digest("policy_finding_content", finding.deterministic_payload())
        expected_id = canonical_digest("policy_finding", {"content_id": expected_content})
        if finding.content_id != expected_content or finding.finding_id != expected_id:
            finding_mismatches += 1
            errors.append(f"finding content ID mismatch: {finding.finding_id}")
    condition_mismatches = 0
    finding_check_ids = {finding.check_id for finding in record.findings}
    for condition in record.conditions:
        expected_content = canonical_digest("acceptance_condition_content", condition.deterministic_payload())
        expected_id = canonical_digest("acceptance_condition", {"content_id": expected_content})
        if condition.content_id != expected_content or condition.condition_id != expected_id:
            condition_mismatches += 1
            errors.append(f"condition content ID mismatch: {condition.condition_id}")
        if condition.source_check_id not in finding_check_ids:
            errors.append(f"condition references unknown check: {condition.source_check_id}")
    count_fields = {
        "passed_check_count": sum(item.status == "passed" for item in record.findings),
        "failed_check_count": sum(item.status == "failed" for item in record.findings),
        "unresolved_check_count": sum(item.status in {"unresolved", "not_checked"} for item in record.findings),
        "not_applicable_check_count": sum(item.status == "not_applicable" for item in record.findings),
        "blocking_finding_count": sum(item.status in {"failed", "unresolved", "not_checked"} and item.severity == "blocking" for item in record.findings),
        "manual_review_finding_count": sum(item.status in {"failed", "unresolved", "not_checked"} and item.severity == "manual_review" for item in record.findings),
        "conditional_finding_count": sum(item.status in {"failed", "unresolved", "not_checked"} and item.severity == "conditional" for item in record.findings),
    }
    for field_name, expected in count_fields.items():
        if getattr(record, field_name) != expected:
            errors.append(f"decision count mismatch: {field_name}")
    unknown_claim_refs: set[str] = set()
    unknown_validation_refs: set[str] = set()
    unknown_artifact_refs: set[str] = set()
    unknown_limitation_refs: set[str] = set()
    if assurance_case is not None:
        if record.assurance_case_id != assurance_case.assurance_case_id: errors.append("assurance case ID mismatch")
        if record.assurance_case_content_id != assurance_case.content_id: errors.append("assurance case content ID mismatch")
        claim_ids = {item.claim_id for item in assurance_case.claims}
        validation_ids = {item.validation_id for item in assurance_case.validation_observations}
        artifact_ids = {item.artifact_id for item in assurance_case.artifact_records}
        limitation_ids = {item.limitation_id for item in assurance_case.limitations}
        unknown_claim_refs = {item for finding in record.findings for item in finding.claim_ids} - claim_ids
        unknown_validation_refs = {item for finding in record.findings for item in finding.validation_ids} - validation_ids
        unknown_artifact_refs = {item for finding in record.findings for item in finding.artifact_ids} - artifact_ids
        unknown_limitation_refs = {item for finding in record.findings for item in finding.limitation_ids} - limitation_ids
        if unknown_claim_refs: errors.append("unknown claim references in findings")
        if unknown_validation_refs: errors.append("unknown validation references in findings")
        if unknown_artifact_refs: errors.append("unknown artifact references in findings")
        if unknown_limitation_refs: errors.append("unknown limitation references in findings")
    expected_content = canonical_digest("review_decision_content", record.deterministic_payload())
    decision_mismatch = int(record.content_id != expected_content)
    if decision_mismatch: errors.append("review decision content ID mismatch")
    expected_id = canonical_digest("review_decision", {"content_id": expected_content})
    decision_id_mismatch = int(record.decision_id != expected_id)
    if decision_id_mismatch: errors.append("review decision ID mismatch")
    provenance_snapshot_mismatches = 0
    provenance_node_mismatches = 0
    provenance_contract_mismatches = 0
    if record.decision_provenance is not None:
        from intentforge.review.provenance import verify_decision_provenance

        provenance_validation = verify_decision_provenance(record, perform_replay=False)
        provenance_snapshot_mismatches = provenance_validation.snapshot_mismatch_count
        provenance_node_mismatches = provenance_validation.execution_node_mismatch_count
        provenance_contract_mismatches = int(not provenance_validation.replay_supported)
        if not provenance_validation.passed:
            errors.extend(f"decision provenance: {item}" for item in provenance_validation.errors)
            errors.extend(f"decision provenance: {item}" for item in provenance_validation.warnings)
    metrics = {
        "finding_content_id_mismatch_count": finding_mismatches,
        "condition_content_id_mismatch_count": condition_mismatches,
        "decision_content_id_mismatch_count": decision_mismatch,
        "decision_id_mismatch_count": decision_id_mismatch,
        "unknown_claim_reference_count": len(unknown_claim_refs),
        "unknown_validation_reference_count": len(unknown_validation_refs),
        "unknown_capability_reference_count": len(unknown_capabilities),
        "unknown_evidence_reference_count": len(unknown_evidence),
        "unknown_rule_reference_count": len(unknown_rules),
        "unknown_artifact_reference_count": len(unknown_artifact_refs),
        "unknown_limitation_reference_count": len(unknown_limitation_refs),
        "provenance_snapshot_mismatch_count": provenance_snapshot_mismatches,
        "provenance_execution_node_mismatch_count": provenance_node_mismatches,
        "provenance_contract_mismatch_count": provenance_contract_mismatches,
    }
    return ReviewDecisionValidationResult(passed=not errors, errors=errors, metrics=metrics)
