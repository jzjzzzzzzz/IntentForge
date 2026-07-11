from __future__ import annotations

from intentforge.review import (
    diff_review_decisions,
    diff_review_variants,
    evaluate_assurance_case,
    get_review_policy,
    render_multi_variant_diff_markdown,
    render_review_diff_markdown,
)
from tests.review_test_helpers import review_resources, standard_case


def _decisions():
    policy = get_review_policy("intentforge_standard_design_review_v1")
    return (
        evaluate_assurance_case(policy, standard_case(), resources=review_resources()),
        evaluate_assurance_case(policy, standard_case(partial=True), resources=review_resources()),
    )


def test_pairwise_delta_markdown_is_deterministic_and_scoped() -> None:
    accepted, conditional = _decisions()
    report = diff_review_decisions(conditional, accepted)
    first = render_review_diff_markdown(report)
    second = render_review_diff_markdown(report)
    assert first == second
    assert "Acceptance Outcome" in first
    assert "acceptance_elevated" in first
    assert "Evaluation Graph Deltas" in first
    assert "does not perform geometric visual diffing" in first
    assert "certified safe" not in first.lower()


def test_multi_variant_markdown_has_outcome_matrix() -> None:
    accepted, conditional = _decisions()
    report = diff_review_variants(accepted, [conditional])
    markdown = render_multi_variant_diff_markdown(report)
    assert "Multi-Variant Review Differential Audit" in markdown
    assert "Outcome Matrix" in markdown
    assert accepted.decision_id in markdown
    assert conditional.decision_id in markdown
