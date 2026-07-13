"""Deterministic declarative exemption matching for review decisions (Phase 31).

The exemption engine is a closed, non-LLM, content-addressable subsystem that
maps one or more ``ExemptionManifest`` records onto the blocking findings of a
``ReviewDecision``. When at least one fully-matching manifest is recorded, the
review state machine deterministically elevates ``rejected_by_policy`` to the
new ``accepted_with_exemption`` status.

The engine itself does NOT mutate decisions; it produces an
``ExemptionEvaluation`` whose references are then projected onto a ``ReviewDecision``
by ``apply_exemptions_to_decision``. All comparisons are performed on the
immutable ``exemption_hash``, the canonical ``content_id``, and the explicit
target predicates emitted by each manifest.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from intentforge.review.exemption_schema import (
    AppliedExemptionReference,
    ExemptionEvaluation,
    ExemptionManifest,
    ExemptionManifestValidationResult,
    ExemptionTarget,
    validate_exemption_manifest,
)
from intentforge.assurance.schema import canonical_digest
from intentforge.review.schema import (
    AcceptanceCondition,
    EXEMPTION_CONDITION_TYPE,
    PolicyFinding,
    ReviewDecision,
)


def load_exemption_manifest(source: ExemptionManifest | dict[str, Any] | str | Path) -> ExemptionManifest:
    """Hydrate an ``ExemptionManifest`` from a JSON path, dict, or model."""

    if isinstance(source, ExemptionManifest):
        return source
    if isinstance(source, dict):
        return ExemptionManifest.model_validate(source)
    path = Path(source)
    if not path.is_file():
        raise ValueError(f"exemption manifest file does not exist: {source}")
    return ExemptionManifest.model_validate_json(path.read_text(encoding="utf-8"))


def _coerce_rule_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_metric_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_identifier_list(values: Iterable[Any]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw).strip() if raw is not None else ""
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def _extract_metric_identifiers(finding: PolicyFinding) -> list[str]:
    candidates: list[str] = []
    for source in (finding.observed_value, finding.expected_value):
        if isinstance(source, Mapping):
            for key in ("metric", "metric_id", "target_metric", "metric_name"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
        elif isinstance(source, str) and ":" in source:
            candidates.append(source.split(":", 1)[1].strip())
    return _coerce_identifier_list(candidates)


def _extract_parameter_identifiers(
    finding: PolicyFinding,
    *,
    package_result: Mapping[str, Any] | None = None,
) -> list[str]:
    candidates: list[str] = []
    for source in (finding.observed_value, finding.expected_value):
        if isinstance(source, Mapping):
            for key in ("parameter", "parameter_id", "topology_parameter", "parameter_name"):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
    if package_result is not None:
        observed = package_result.get("observed_values") if isinstance(package_result, Mapping) else None
        if isinstance(observed, Mapping):
            for key, value in observed.items():
                if isinstance(value, Mapping):
                    param_value = value.get("parameter")
                    if isinstance(param_value, str) and param_value.strip():
                        candidates.append(param_value.strip())
    return _coerce_identifier_list(candidates)


def _target_matches_rule(target: ExemptionTarget, finding: PolicyFinding) -> bool:
    rule_ids = _coerce_identifier_list(finding.rule_ids)
    if target.identifier in rule_ids:
        return True
    # Fall back to the policy's required rule ids when the check is a
    # ``required_rule_reference`` (the finding only records the *present* set,
    # so the missing rules are not exposed via ``rule_ids``). The ``expected_value``
    # payload always carries the canonical required rule list.
    expected = finding.expected_value
    if isinstance(expected, Mapping):
        required = expected.get("required")
        if isinstance(required, list):
            if target.identifier in {str(item) for item in required}:
                return True
    return False


def _target_matches_metric(
    target: ExemptionTarget,
    finding: PolicyFinding,
    package_result: Mapping[str, Any] | None,
) -> bool:
    metrics = _extract_metric_identifiers(finding)
    if not metrics:
        return False
    return target.identifier in metrics


def _target_matches_parameter(
    target: ExemptionTarget,
    finding: PolicyFinding,
    package_result: Mapping[str, Any] | None,
) -> bool:
    parameters = _extract_parameter_identifiers(finding, package_result=package_result)
    if not parameters:
        return False
    return target.identifier in parameters


def evaluate_exemption_for_finding(
    manifest: ExemptionManifest,
    finding: PolicyFinding,
    *,
    package_result: Mapping[str, Any] | None = None,
) -> tuple[bool, list[str], list[str], list[str]]:
    """Return ``(matched, matched_rules, matched_metrics, matched_parameters)``."""

    matched_rules: list[str] = []
    matched_metrics: list[str] = []
    matched_parameters: list[str] = []
    if finding.severity != "blocking":
        return False, matched_rules, matched_metrics, matched_parameters
    if finding.status not in {"failed", "unresolved", "not_checked"}:
        return False, matched_rules, matched_metrics, matched_parameters
    matches_any = False
    for target in manifest.targets:
        if target.kind == "rule_id" and _target_matches_rule(target, finding):
            matched_rules.append(target.identifier)
            matches_any = True
        elif target.kind == "metric" and _target_matches_metric(target, finding, package_result):
            matched_metrics.append(target.identifier)
            matches_any = True
        elif target.kind == "parameter" and _target_matches_parameter(target, finding, package_result):
            matched_parameters.append(target.identifier)
            matches_any = True
    return matches_any, matched_rules, matched_metrics, matched_parameters


def match_exemptions(
    decision: ReviewDecision,
    manifests: Sequence[ExemptionManifest],
    *,
    package_result: Mapping[str, Any] | None = None,
) -> ExemptionEvaluation:
    """Match every manifest against the decision's blocking findings.

    The matching is purely deterministic: it walks the manifest target list and
    confirms each target's ``identifier`` is consistent with the finding's
    ``rule_ids``, computed metric identifiers, or computed parameter
    identifiers. A manifest matches a finding only if every target is satisfied.
    """

    if not manifests:
        return ExemptionEvaluation(
            decision_id=decision.decision_id,
            elevated_to_exemption=False,
            applied_references=[],
            unmatched_manifest_ids=[],
        )
    blocking_findings = [
        finding for finding in decision.findings
        if finding.severity == "blocking"
        and finding.status in {"failed", "unresolved", "not_checked"}
    ]
    applied: list[AppliedExemptionReference] = []
    seen_references: set[str] = set()
    unmatched: list[str] = []
    candidate_manifest_ids: set[str] = {manifest.exemption_id for manifest in manifests}
    matched_manifest_ids: set[str] = set()
    for finding in blocking_findings:
        for manifest in manifests:
            matched, rule_hits, metric_hits, parameter_hits = evaluate_exemption_for_finding(
                manifest, finding, package_result=package_result,
            )
            if not matched:
                if manifest.exemption_id not in matched_manifest_ids:
                    unmatched.append(manifest.exemption_id)
                continue
            matched_manifest_ids.add(manifest.exemption_id)
            reference_payload = {
                "exemption_id": manifest.exemption_id,
                "exemption_hash": manifest.exemption_hash,
                "applying_entity": manifest.authorizing_entity,
                "rationale": manifest.rationale,
                "matched_check_id": finding.check_id,
                "matched_rule_ids": sorted(set(rule_hits)),
                "matched_metric_ids": sorted(set(metric_hits)),
                "matched_parameter_ids": sorted(set(parameter_hits)),
            }
            reference_payload["reference_id"] = "applied:" + manifest.exemption_id + ":" + finding.check_id
            reference = AppliedExemptionReference.model_validate(reference_payload)
            if reference.content_id in seen_references:
                continue
            seen_references.add(reference.content_id)
            applied.append(reference)
    unmatched_set = sorted(
        {
            manifest.exemption_id
            for manifest in manifests
            if manifest.exemption_id not in matched_manifest_ids
        }
    )
    elevated = bool(applied) and decision.decision_status == "rejected_by_policy"
    return ExemptionEvaluation(
        decision_id=decision.decision_id,
        elevated_to_exemption=elevated,
        applied_references=sorted(applied, key=lambda item: item.reference_id),
        unmatched_manifest_ids=unmatched_set,
    )


def _build_exemption_condition(reference: AppliedExemptionReference) -> AcceptanceCondition:
    payload = {
        "condition_id": "pending",
        "content_id": "pending",
        "source_check_id": reference.matched_check_id,
        "title": f"Exemption applied: {reference.exemption_id}",
        "description": (
            f"Blocking finding {reference.matched_check_id} overridden by exemption "
            f"{reference.exemption_id} ({reference.applying_entity}). Rationale: "
            f"{reference.rationale}"
        ),
        "condition_type": EXEMPTION_CONDITION_TYPE,
        "blocking": False,
        "required_action": (
            "Acknowledge the externally authorised exemption recorded in the linked manifest"
        ),
        "related_claim_ids": [],
        "related_validation_ids": [],
        "related_limitation_ids": [],
    }
    from intentforge.assurance.schema import canonical_digest

    content_id = canonical_digest(
        "exemption_condition_content",
        {
            "source_check_id": payload["source_check_id"],
            "title": payload["title"],
            "description": payload["description"],
            "condition_type": payload["condition_type"],
            "required_action": payload["required_action"],
        },
    )
    payload["content_id"] = content_id
    payload["condition_id"] = canonical_digest(
        "exemption_condition",
        {"content_id": content_id},
    )
    return AcceptanceCondition.model_validate(payload)


def apply_exemptions_to_decision(
    decision: ReviewDecision,
    manifests: Sequence[ExemptionManifest],
    *,
    package_result: Mapping[str, Any] | None = None,
) -> ReviewDecision:
    """Return a new ``ReviewDecision`` elevated by matching exemption manifests.

    The function does not mutate ``decision``: it computes the deterministic
    elevated status, attaches the new ``applied_exemption_references`` field,
    and emits the corresponding ``policy_acknowledgement_required`` condition
    entries. The output goes through the standard ``model_validate`` pipeline so
    that identity, ordering, and content-address invariants are preserved.
    """

    evaluation = match_exemptions(decision, manifests, package_result=package_result)
    new_status = decision.decision_status
    new_conditions = list(decision.conditions)
    for reference in evaluation.applied_references:
        new_conditions.append(_build_exemption_condition(reference))
    new_conditions.sort(key=lambda item: item.condition_id)
    elevated = bool(evaluation.applied_references) and decision.decision_status == "rejected_by_policy"
    if elevated:
        new_status = "accepted_with_exemption"
    elevated_reason = (
        "deterministic elevation to accepted_with_exemption"
        if elevated
        else decision.exemption_elevation_reason
    )
    counters = decision.model_dump(mode="json")
    counters["applied_exemption_references"] = [
        reference.model_dump(mode="json") for reference in evaluation.applied_references
    ]
    counters["exemption_evaluation_content_id"] = evaluation.content_address
    counters["exemption_elevation_reason"] = elevated_reason
    counters["decision_status"] = new_status
    counters["conditions"] = [
        condition.model_dump(mode="json") for condition in new_conditions
    ]
    counters["limitations"] = sorted(
        set(list(decision.limitations) + [
            f"Exemption {reference.exemption_id} overrides check {reference.matched_check_id}"
            for reference in evaluation.applied_references
        ])
    )
    rebuilt = ReviewDecision.model_validate(counters)
    # Recompute the content address so cryptographic identity reflects the new
    # applied exemption references and elevated status.
    rebuilt_content_id = canonical_digest("review_decision_content", rebuilt.deterministic_payload())
    rebuilt_decision_id = canonical_digest("review_decision", {"content_id": rebuilt_content_id})
    return rebuilt.model_copy(update={
        "decision_id": rebuilt_decision_id,
        "content_id": rebuilt_content_id,
    })


def validate_manifest_set(manifests: Iterable[ExemptionManifest | dict[str, Any]]) -> ExemptionManifestValidationResult:
    """Aggregate validation summary for an iterable of manifests."""

    manifest_models: list[ExemptionManifest] = []
    for item in manifests:
        if isinstance(item, ExemptionManifest):
            manifest_models.append(item)
        else:
            try:
                manifest_models.append(ExemptionManifest.model_validate(item))
            except (ValueError, TypeError):
                return ExemptionManifestValidationResult(
                    passed=False,
                    errors=[f"failed to parse exemption manifest: {item!r}"],
                )
    if not manifest_models:
        return ExemptionManifestValidationResult(passed=True, errors=[], metrics={"manifest_count": 0})
    errors: list[str] = []
    warnings: list[str] = []
    aggregated_metrics: dict[str, int] = {"manifest_count": len(manifest_models)}
    for model in manifest_models:
        result = validate_exemption_manifest(model)
        if not result.passed:
            errors.extend(result.errors)
        warnings.extend(result.warnings)
        for key, value in result.metrics.items():
            aggregated_metrics[key] = aggregated_metrics.get(key, 0) + value
    return ExemptionManifestValidationResult(
        passed=not errors,
        manifest_id=manifest_models[0].exemption_id if manifest_models else None,
        exemption_hash=manifest_models[0].exemption_hash if manifest_models else None,
        content_id=manifest_models[0].content_id if manifest_models else None,
        errors=errors,
        warnings=warnings,
        metrics=aggregated_metrics,
    )


def serialise_evaluation(evaluation: ExemptionEvaluation) -> str:
    """Return the canonical JSON representation of an ``ExemptionEvaluation``."""

    return json.dumps(evaluation.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


__all__ = [
    "evaluate_exemption_for_finding",
    "load_exemption_manifest",
    "match_exemptions",
    "apply_exemptions_to_decision",
    "serialise_evaluation",
    "validate_manifest_set",
]
