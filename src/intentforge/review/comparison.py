"""Deterministic structural review-decision and multi-variant differential audits."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from intentforge.assurance.schema import canonical_digest
from intentforge.review.diff_schema import (
    MultiVariantReviewDiff,
    ReviewDecisionDiff,
    SemanticDecisionDelta,
)
from intentforge.review.schema import ReviewDecision


_ACCEPTED_STATUSES = {"accepted_within_declared_scope", "accepted_with_conditions"}
_SECURITY_SEVERITIES = {"blocking", "manual_review", "conditional"}


def load_review_decision_source(source: ReviewDecision | dict | str | Path) -> ReviewDecision:
    """Load a decision JSON file or validated audit-package directory."""

    if isinstance(source, ReviewDecision):
        return source
    if isinstance(source, dict):
        return ReviewDecision.model_validate(source)
    path = Path(source)
    if path.is_dir():
        from intentforge.assurance.audit_package import validate_audit_package

        validation = validate_audit_package(path)
        if not validation.get("passed"):
            raise ValueError("invalid audit package: " + "; ".join(validation.get("errors", [])))
        path = path / "review_decision.json"
    if not path.is_file():
        raise ValueError(f"review decision source does not exist: {source}")
    return ReviewDecision.model_validate_json(path.read_text(encoding="utf-8"))


def _changed_fields(before: Any, after: Any) -> list[str]:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return ["value"] if before != after else []
    return sorted(
        key for key in set(before).union(after)
        if before.get(key) != after.get(key)
    )


def _transition(before: str, after: str) -> str:
    if before == after:
        return "unchanged"
    if before in _ACCEPTED_STATUSES and after in _ACCEPTED_STATUSES:
        if before == "accepted_with_conditions" and after == "accepted_within_declared_scope":
            return "acceptance_elevated"
        return "acceptance_constrained"
    if before not in _ACCEPTED_STATUSES and after in _ACCEPTED_STATUSES:
        return "acceptance_elevated"
    if before in _ACCEPTED_STATUSES and after not in _ACCEPTED_STATUSES:
        return "acceptance_constrained"
    return "status_changed"


def _transition_impact(transition: str) -> str:
    return {
        "unchanged": "none",
        "acceptance_elevated": "more_permissive",
        "acceptance_constrained": "more_restrictive",
        "status_changed": "structural_change",
    }[transition]


def _delta(
    *,
    category: str,
    entity_key: str,
    before: Any,
    after: Any,
    summary_code: str,
    security_relevant: bool = False,
    compliance_impact: str = "structural_change",
) -> SemanticDecisionDelta | None:
    if before == after:
        return None
    change_type = "added" if before is None else "removed" if after is None else "modified"
    return SemanticDecisionDelta(
        category=category,
        entity_key=entity_key,
        change_type=change_type,
        before=before,
        after=after,
        changed_fields=_changed_fields(before, after),
        compliance_impact=compliance_impact,
        security_relevant=security_relevant,
        summary_code=summary_code,
    )


def _policy_payload(decision: ReviewDecision) -> dict[str, Any]:
    provenance = decision.decision_provenance
    if provenance is not None:
        try:
            return dict(provenance.snapshot("review_policy").payload)
        except (ValueError, TypeError):
            pass
    return {
        "policy_id": decision.policy_id,
        "policy_version": decision.policy_version,
        "content_id": decision.policy_content_id,
        "checks": [],
    }


def _policy_checks(decision: ReviewDecision) -> dict[str, dict[str, Any]]:
    checks = _policy_payload(decision).get("checks", [])
    return {
        str(item["check_id"]): item
        for item in checks
        if isinstance(item, dict) and item.get("check_id")
    }


def _execution_graph(decision: ReviewDecision) -> dict[str, dict[str, Any]]:
    provenance = decision.decision_provenance
    if provenance is not None:
        result = {}
        for item in provenance.execution_nodes:
            data = item.model_dump(mode="json")
            for field_name in (
                "node_id", "content_id", "input_content_ids", "output_content_ids"
            ):
                data.pop(field_name, None)
            result[item.node_key] = data
        return result
    return {
        f"check:{item.check_id}": {
            "node_key": f"check:{item.check_id}",
            "node_type": "check_evaluation",
            "check_id": item.check_id,
            "status": item.status,
            "observed_value": item.observed_value,
            "expected_value": item.expected_value,
        }
        for item in decision.findings
    }


def _finding_index(decision: ReviewDecision) -> dict[str, dict[str, Any]]:
    result = {}
    for item in decision.findings:
        data = item.model_dump(mode="json")
        for field_name in (
            "finding_id",
            "content_id",
            "claim_ids",
            "argument_ids",
            "validation_ids",
        ):
            data.pop(field_name, None)
        result[item.check_id] = data
    return result


def _condition_index(decision: ReviewDecision) -> dict[str, dict[str, Any]]:
    result = {}
    for item in decision.conditions:
        data = item.model_dump(mode="json")
        for field_name in (
            "condition_id",
            "content_id",
            "related_claim_ids",
            "related_validation_ids",
            "related_limitation_ids",
        ):
            data.pop(field_name, None)
        result[item.source_check_id] = data
    return result


def _append_index_deltas(
    deltas: list[SemanticDecisionDelta],
    *,
    category: str,
    before: dict[str, Any],
    after: dict[str, Any],
    summary_code: str,
    security_relevant: bool | Any,
) -> None:
    for key in sorted(set(before).union(after)):
        before_value = before.get(key)
        after_value = after.get(key)
        relevant = security_relevant(before_value, after_value) if callable(security_relevant) else security_relevant
        impact = "structural_change"
        if category in {"finding", "condition"}:
            if before_value is None:
                impact = "more_restrictive"
            elif after_value is None:
                impact = "more_permissive"
        item = _delta(
            category=category,
            entity_key=key,
            before=before_value,
            after=after_value,
            summary_code=summary_code,
            security_relevant=bool(relevant),
            compliance_impact=impact,
        )
        if item is not None:
            deltas.append(item)


def _append_reference_deltas(
    deltas: list[SemanticDecisionDelta],
    *,
    category: str,
    before: list[str],
    after: list[str],
) -> None:
    before_set = set(before)
    after_set = set(after)
    for key in sorted(before_set - after_set):
        deltas.append(SemanticDecisionDelta(
            category=category,
            entity_key=key,
            change_type="removed",
            before={"referenced": True},
            after=None,
            changed_fields=["referenced"],
            compliance_impact="structural_change",
            security_relevant=category in {"evidence", "capability"},
            summary_code=f"{category}_reference_removed",
        ))
    for key in sorted(after_set - before_set):
        deltas.append(SemanticDecisionDelta(
            category=category,
            entity_key=key,
            change_type="added",
            before=None,
            after={"referenced": True},
            changed_fields=["referenced"],
            compliance_impact="structural_change",
            security_relevant=category in {"evidence", "capability"},
            summary_code=f"{category}_reference_added",
        ))


def diff_review_decisions(
    baseline: ReviewDecision | dict | str | Path,
    candidate: ReviewDecision | dict | str | Path,
    *,
    runtime_metadata: dict[str, Any] | None = None,
) -> ReviewDecisionDiff:
    """Compare keyed policy graphs, findings, conditions, and outcomes."""

    first = load_review_decision_source(baseline)
    second = load_review_decision_source(candidate)
    deltas: list[SemanticDecisionDelta] = []
    subject_before = {
        "cad_family": first.cad_family,
        "operation": first.operation,
        "subject_type": first.subject_type,
        "assurance_profile": first.assurance_profile,
        "assurance_case_content_id": first.assurance_case_content_id,
    }
    subject_after = {
        "cad_family": second.cad_family,
        "operation": second.operation,
        "subject_type": second.subject_type,
        "assurance_profile": second.assurance_profile,
        "assurance_case_content_id": second.assurance_case_content_id,
    }
    subject_delta = _delta(
        category="subject",
        entity_key="review_subject",
        before=subject_before,
        after=subject_after,
        summary_code="review_subject_changed",
    )
    if subject_delta is not None:
        deltas.append(subject_delta)

    policy_before = _policy_payload(first)
    policy_after = _policy_payload(second)
    active_policy_before = {
        "policy_id": first.policy_id,
        "policy_version": first.policy_version,
        "content_id": first.policy_content_id,
    }
    active_policy_after = {
        "policy_id": second.policy_id,
        "policy_version": second.policy_version,
        "content_id": second.policy_content_id,
    }
    policy_delta = _delta(
        category="policy",
        entity_key="active_policy",
        before=active_policy_before,
        after=active_policy_after,
        summary_code="active_policy_changed",
        security_relevant=True,
    )
    if policy_delta is not None:
        deltas.append(policy_delta)
    policy_checks_before = _policy_checks(first)
    policy_checks_after = _policy_checks(second)
    _append_index_deltas(
        deltas,
        category="policy",
        before=policy_checks_before,
        after=policy_checks_after,
        summary_code="policy_check_configuration_changed",
        security_relevant=True,
    )

    graph_before = _execution_graph(first)
    graph_after = _execution_graph(second)
    _append_index_deltas(
        deltas,
        category="evaluation_graph",
        before=graph_before,
        after=graph_after,
        summary_code="evaluation_graph_node_changed",
        security_relevant=lambda before, after: any(
            (item or {}).get("node_type") in {"check_evaluation", "decision_precedence"}
            for item in (before, after)
        ),
    )

    findings_before = _finding_index(first)
    findings_after = _finding_index(second)
    _append_index_deltas(
        deltas,
        category="finding",
        before=findings_before,
        after=findings_after,
        summary_code="policy_finding_changed",
        security_relevant=lambda before, after: any(
            (item or {}).get("severity") in _SECURITY_SEVERITIES for item in (before, after)
        ),
    )
    conditions_before = _condition_index(first)
    conditions_after = _condition_index(second)
    _append_index_deltas(
        deltas,
        category="condition",
        before=conditions_before,
        after=conditions_after,
        summary_code="acceptance_condition_changed",
        security_relevant=True,
    )

    transition = _transition(first.decision_status, second.decision_status)
    outcome_delta = _delta(
        category="outcome",
        entity_key="decision_status",
        before={"status": first.decision_status},
        after={"status": second.decision_status},
        summary_code=f"decision_{transition}",
        security_relevant=True,
        compliance_impact=_transition_impact(transition),
    )
    if outcome_delta is not None:
        deltas.append(outcome_delta)
    for category, before_refs, after_refs in (
        ("capability", first.relevant_capability_ids, second.relevant_capability_ids),
        ("evidence", first.relevant_evidence_ids, second.relevant_evidence_ids),
        ("rule", first.relevant_rule_ids, second.relevant_rule_ids),
        ("limitation", first.limitations, second.limitations),
    ):
        _append_reference_deltas(
            deltas,
            category=category,
            before=before_refs,
            after=after_refs,
        )
    provenance_before = None if first.decision_provenance is None else {
        "schema_version": first.decision_provenance.schema_version,
        "evaluator_version": first.decision_provenance.evaluator_version,
        "check_registry_content_id": first.decision_provenance.check_registry_content_id,
        "decision_strategy_content_id": first.decision_provenance.decision_strategy_content_id,
        "provenance_id": first.decision_provenance.provenance_id,
    }
    provenance_after = None if second.decision_provenance is None else {
        "schema_version": second.decision_provenance.schema_version,
        "evaluator_version": second.decision_provenance.evaluator_version,
        "check_registry_content_id": second.decision_provenance.check_registry_content_id,
        "decision_strategy_content_id": second.decision_provenance.decision_strategy_content_id,
        "provenance_id": second.decision_provenance.provenance_id,
    }
    provenance_delta = _delta(
        category="provenance",
        entity_key="decision_provenance",
        before=provenance_before,
        after=provenance_after,
        summary_code="decision_provenance_changed",
        security_relevant=True,
    )
    if provenance_delta is not None:
        deltas.append(provenance_delta)

    common_checks = set(findings_before).intersection(findings_after)
    modified_checks = sorted(
        check_id for check_id in common_checks
        if findings_before[check_id] != findings_after[check_id]
        or policy_checks_before.get(check_id) != policy_checks_after.get(check_id)
        or graph_before.get(f"check:{check_id}") != graph_after.get(f"check:{check_id}")
    )
    common_conditions = set(conditions_before).intersection(conditions_after)
    modified_conditions = sorted(
        check_id for check_id in common_conditions
        if conditions_before[check_id] != conditions_after[check_id]
    )
    deltas.sort(key=lambda item: (item.category, item.entity_key, item.delta_id))
    return ReviewDecisionDiff(
        baseline_decision_id=first.decision_id,
        baseline_content_id=first.content_id,
        candidate_decision_id=second.decision_id,
        candidate_content_id=second.content_id,
        identical=not deltas,
        decision_transition=transition,
        baseline_status=first.decision_status,
        candidate_status=second.decision_status,
        policy_changed=active_policy_before != active_policy_after or policy_before != policy_after,
        evaluation_graph_changed=graph_before != graph_after,
        deltas=deltas,
        added_check_ids=sorted(set(findings_after) - set(findings_before)),
        removed_check_ids=sorted(set(findings_before) - set(findings_after)),
        modified_check_ids=modified_checks,
        added_condition_check_ids=sorted(set(conditions_after) - set(conditions_before)),
        removed_condition_check_ids=sorted(set(conditions_before) - set(conditions_after)),
        modified_condition_check_ids=modified_conditions,
        summary={
            "delta_count": len(deltas),
            "security_compliance_change_count": sum(item.security_relevant for item in deltas),
            "policy_check_count_before": len(policy_checks_before),
            "policy_check_count_after": len(policy_checks_after),
            "execution_node_count_before": len(graph_before),
            "execution_node_count_after": len(graph_after),
            "finding_count_before": len(findings_before),
            "finding_count_after": len(findings_after),
            "condition_count_before": len(conditions_before),
            "condition_count_after": len(conditions_after),
        },
        runtime_metadata=runtime_metadata or {},
    )


def diff_review_variants(
    baseline: ReviewDecision | dict | str | Path,
    variants: Iterable[ReviewDecision | dict | str | Path],
    *,
    runtime_metadata: dict[str, Any] | None = None,
) -> MultiVariantReviewDiff:
    """Compare multiple variants against one fixed deterministic baseline."""

    first = load_review_decision_source(baseline)
    candidates = [load_review_decision_source(item) for item in variants]
    if not candidates:
        raise ValueError("at least one review decision variant is required")
    if len({item.decision_id for item in candidates}) != len(candidates):
        raise ValueError("duplicate review decision variants are not allowed")
    diffs = sorted(
        [diff_review_decisions(first, item) for item in candidates],
        key=lambda item: item.candidate_decision_id,
    )
    all_decisions = [first, *sorted(candidates, key=lambda item: item.decision_id)]
    return MultiVariantReviewDiff(
        baseline_decision_id=first.decision_id,
        variant_decision_ids=[item.candidate_decision_id for item in diffs],
        pairwise_diffs=diffs,
        outcome_matrix={item.decision_id: item.decision_status for item in all_decisions},
        policy_matrix={
            item.decision_id: {
                "policy_id": item.policy_id,
                "policy_version": item.policy_version,
                "policy_content_id": item.policy_content_id,
            }
            for item in all_decisions
        },
        identical_variant_count=sum(item.identical for item in diffs),
        elevated_variant_count=sum(item.decision_transition == "acceptance_elevated" for item in diffs),
        constrained_variant_count=sum(item.decision_transition == "acceptance_constrained" for item in diffs),
        changed_variant_count=sum(item.decision_transition == "status_changed" for item in diffs),
        security_compliance_change_count=sum(len(item.security_compliance_delta_ids) for item in diffs),
        summary={
            "variant_count": len(diffs),
            "all_identical": all(item.identical for item in diffs),
            "deterministic_structural_comparison": True,
        },
        runtime_metadata=runtime_metadata or {},
    )


def compare_review_decisions(first: ReviewDecision | dict, second: ReviewDecision | dict) -> dict[str, Any]:
    """Backward-compatible comparison with additive semantic-diff metadata."""

    a = load_review_decision_source(first)
    b = load_review_decision_source(second)
    fields = {
        "policy": (
            {"id": a.policy_id, "version": a.policy_version, "content_id": a.policy_content_id},
            {"id": b.policy_id, "version": b.policy_version, "content_id": b.policy_content_id},
        ),
        "assurance_case": (
            {"id": a.assurance_case_id, "content_id": a.assurance_case_content_id},
            {"id": b.assurance_case_id, "content_id": b.assurance_case_content_id},
        ),
        "decision_status": (a.decision_status, b.decision_status),
        "findings": (
            [item.model_dump(mode="json") for item in a.findings],
            [item.model_dump(mode="json") for item in b.findings],
        ),
        "conditions": (
            [item.model_dump(mode="json") for item in a.conditions],
            [item.model_dump(mode="json") for item in b.conditions],
        ),
        "limitations": (a.limitations, b.limitations),
        "capabilities": (a.relevant_capability_ids, b.relevant_capability_ids),
        "evidence": (a.relevant_evidence_ids, b.relevant_evidence_ids),
        "rules": (a.relevant_rule_ids, b.relevant_rule_ids),
    }
    changes = {
        name: {"before": values[0], "after": values[1]}
        for name, values in fields.items()
        if values[0] != values[1]
    }
    identity = {"first": a.content_id, "second": b.content_id, "changed_fields": sorted(changes)}
    semantic = diff_review_decisions(a, b)
    return {
        "comparison_id": canonical_digest("review_comparison", identity),
        "identical": not changes,
        "first_decision_id": a.decision_id,
        "second_decision_id": b.decision_id,
        "changed_fields": sorted(changes),
        "changes": changes,
        "semantic_diff_id": semantic.diff_id,
        "decision_transition": semantic.decision_transition,
        "security_compliance_change_count": len(semantic.security_compliance_delta_ids),
    }
