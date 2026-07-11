"""Validation for assurance cases without re-running CAD generation."""

from __future__ import annotations

from intentforge.assurance.claims import make_claim
from intentforge.assurance.schema import AssuranceCase, AssuranceValidationResult, canonical_digest, safe_relative_path
from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.evidence_registry import load_evidence_definitions
from intentforge.knowledge.rules import RuleRegistry


def validate_assurance_case(
    case: AssuranceCase | dict,
    *,
    capability_ids: set[str] | None = None,
    evidence_ids: set[str] | None = None,
    rule_ids: set[str] | None = None,
) -> AssuranceValidationResult:
    record = case if isinstance(case, AssuranceCase) else AssuranceCase.model_validate(case)
    errors: list[str] = []
    if capability_ids is None:
        capability_ids = {item.capability_id for item in load_capability_manifest().capabilities}
    if evidence_ids is None:
        evidence_ids = {item.evidence_id for item in load_evidence_definitions()}
    if rule_ids is None:
        rule_ids = {item.id for item in RuleRegistry.load().rules}
    unknown_caps = sorted(set(record.capability_references) - capability_ids)
    unknown_evidence = sorted(set(record.evidence_references) - evidence_ids)
    unknown_rules = sorted({item["rule_id"] for item in record.rule_references} - rule_ids)
    if unknown_caps: errors.append(f"unknown capability references: {', '.join(unknown_caps)}")
    if unknown_evidence: errors.append(f"unknown evidence references: {', '.join(unknown_evidence)}")
    if unknown_rules: errors.append(f"unknown rule references: {', '.join(unknown_rules)}")
    claim_ids = {item.claim_id for item in record.claims}
    argument_ids = {item.argument_id for item in record.arguments}
    validation_ids = {item.validation_id for item in record.validation_observations}
    artifact_ids = {item.artifact_id for item in record.artifact_records}
    for claim in record.claims:
        if set(claim.argument_ids) - argument_ids: errors.append(f"claim {claim.claim_id} references unknown arguments")
        if set(claim.supporting_validation_ids) - validation_ids: errors.append(f"claim {claim.claim_id} references unknown validations")
        if set(claim.supporting_artifact_ids) - artifact_ids: errors.append(f"claim {claim.claim_id} references unknown artifacts")
        if claim.claim_type == "geometry_valid" and not claim.supporting_validation_ids:
            errors.append("geometry_valid claim requires a geometry validation observation")
        expected_claim, expected_argument = make_claim(
            claim.claim_type, family=claim.family, status=claim.status, stages=claim.stages,
            capability_ids=claim.capability_ids, evidence_ids=claim.supporting_evidence_ids,
            validation_ids=claim.supporting_validation_ids, artifact_ids=claim.supporting_artifact_ids,
            rule_ids=claim.rule_ids, limitations=claim.limitations, required_review=claim.required_review,
        )
        if claim.content_id != expected_claim.content_id or claim.claim_id != expected_claim.claim_id:
            errors.append(f"claim content ID mismatch: {claim.claim_id}")
        linked = [item for item in record.arguments if item.argument_id in claim.argument_ids]
        if len(linked) == 1 and (
            linked[0].content_id != expected_argument.content_id or linked[0].argument_id != expected_argument.argument_id
        ):
            errors.append(f"argument content ID mismatch: {linked[0].argument_id}")
    for argument in record.arguments:
        if argument.claim_id not in claim_ids: errors.append(f"argument {argument.argument_id} references unknown claim")
    unsafe_paths = 0
    for artifact in record.artifact_records:
        try: safe_relative_path(artifact.path)
        except ValueError:
            unsafe_paths += 1; errors.append(f"unsafe artifact path: {artifact.path}")
    expected_content = canonical_digest("assurance_content", record.deterministic_payload())
    if record.content_id != expected_content: errors.append("assurance content ID mismatch")
    if record.assurance_case_id != canonical_digest("assurance_case", {"content_id": record.content_id}):
        errors.append("assurance case ID mismatch")
    missing_profile = 0
    if record.profile in {"standard", "full"} and record.overall_assurance_status != "assurance_complete_with_limitations":
        if not any(item.validation_type == "geometry_validation" for item in record.validation_observations):
            missing_profile += 1; errors.append("standard/full assurance requires geometry validation unless intentionally rejected")
    metrics = {
        "invalid_capability_reference_count": len(unknown_caps), "invalid_evidence_reference_count": len(unknown_evidence),
        "invalid_rule_reference_count": len(unknown_rules), "unsafe_artifact_path_count": unsafe_paths,
        "missing_required_validation_count": missing_profile,
        "claim_content_id_mismatch_count": sum("claim content ID mismatch" in item for item in errors),
        "argument_content_id_mismatch_count": sum("argument content ID mismatch" in item for item in errors),
        "assurance_case_id_mismatch_count": sum("assurance case ID mismatch" in item for item in errors),
    }
    return AssuranceValidationResult(passed=not errors, errors=errors, metrics=metrics)
