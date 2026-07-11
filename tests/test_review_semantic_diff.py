from __future__ import annotations

from intentforge.review import (
    diff_review_decisions,
    diff_review_variants,
    evaluate_assurance_case,
    get_review_policy,
)
from tests.review_test_helpers import review_resources, standard_case


def _accepted():
    return evaluate_assurance_case(
        get_review_policy("intentforge_standard_design_review_v1"),
        standard_case(),
        resources=review_resources(),
    )


def _conditional():
    return evaluate_assurance_case(
        get_review_policy("intentforge_standard_design_review_v1"),
        standard_case(partial=True),
        resources=review_resources(),
    )


def test_identical_decision_has_no_structural_delta() -> None:
    decision = _accepted()
    result = diff_review_decisions(decision, decision)
    assert result.identical
    assert result.decision_transition == "unchanged"
    assert result.deltas == []


def test_conditional_to_accepted_transition_is_elevated() -> None:
    result = diff_review_decisions(_conditional(), _accepted())
    assert result.decision_transition == "acceptance_elevated"
    outcome = next(item for item in result.deltas if item.category == "outcome")
    assert outcome.compliance_impact == "more_permissive"
    assert outcome.security_relevant


def test_accepted_to_conditional_transition_is_constrained() -> None:
    result = diff_review_decisions(_accepted(), _conditional())
    assert result.decision_transition == "acceptance_constrained"
    assert result.modified_check_ids
    assert any(item.category == "finding" for item in result.deltas)
    assert any(item.category == "condition" for item in result.deltas)
    assert result.evaluation_graph_changed


def test_policy_version_and_content_changes_are_structural() -> None:
    accepted = _accepted()
    changed = accepted.model_copy(update={"policy_version": "1.1", "policy_content_id": "review_policy_changed"})
    result = diff_review_decisions(accepted, changed)
    assert result.policy_changed
    assert any(item.category == "policy" for item in result.deltas)


def test_multi_variant_audit_keeps_baseline_fixed_and_stable() -> None:
    baseline = _accepted()
    conditional = _conditional()
    l_variant = evaluate_assurance_case(
        get_review_policy("intentforge_standard_design_review_v1"),
        standard_case("l_bracket"),
        resources=review_resources(),
    )
    first = diff_review_variants(baseline, [conditional, l_variant])
    second = diff_review_variants(baseline, [l_variant, conditional])
    assert first.audit_id == second.audit_id
    assert first.content_id == second.content_id
    assert all(item.baseline_decision_id == baseline.decision_id for item in first.pairwise_diffs)
    assert first.summary["variant_count"] == 2


def test_diff_is_structured_and_does_not_compare_markdown() -> None:
    result = diff_review_decisions(_accepted(), _conditional())
    assert all(item.summary_code for item in result.deltas)
    assert all(item.entity_key for item in result.deltas)
    assert all("markdown" not in field for item in result.deltas for field in item.changed_fields)
