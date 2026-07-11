"""Structured deterministic comparisons of review decisions."""

from __future__ import annotations

from typing import Any

from intentforge.assurance.schema import canonical_digest
from intentforge.review.schema import ReviewDecision


def compare_review_decisions(first: ReviewDecision | dict, second: ReviewDecision | dict) -> dict[str, Any]:
    a = first if isinstance(first, ReviewDecision) else ReviewDecision.model_validate(first)
    b = second if isinstance(second, ReviewDecision) else ReviewDecision.model_validate(second)
    fields = {
        "policy": ({"id": a.policy_id, "version": a.policy_version, "content_id": a.policy_content_id},
                   {"id": b.policy_id, "version": b.policy_version, "content_id": b.policy_content_id}),
        "assurance_case": ({"id": a.assurance_case_id, "content_id": a.assurance_case_content_id},
                           {"id": b.assurance_case_id, "content_id": b.assurance_case_content_id}),
        "decision_status": (a.decision_status, b.decision_status),
        "findings": ([item.model_dump(mode="json") for item in a.findings], [item.model_dump(mode="json") for item in b.findings]),
        "conditions": ([item.model_dump(mode="json") for item in a.conditions], [item.model_dump(mode="json") for item in b.conditions]),
        "limitations": (a.limitations, b.limitations),
        "capabilities": (a.relevant_capability_ids, b.relevant_capability_ids),
        "evidence": (a.relevant_evidence_ids, b.relevant_evidence_ids),
        "rules": (a.relevant_rule_ids, b.relevant_rule_ids),
    }
    changes = {
        name: {"before": values[0], "after": values[1]}
        for name, values in fields.items() if values[0] != values[1]
    }
    identity = {"first": a.content_id, "second": b.content_id, "changed_fields": sorted(changes)}
    return {
        "comparison_id": canonical_digest("review_comparison", identity),
        "identical": not changes,
        "first_decision_id": a.decision_id,
        "second_decision_id": b.decision_id,
        "changed_fields": sorted(changes),
        "changes": changes,
    }
