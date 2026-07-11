from pathlib import Path

import pytest

from intentforge.assurance import build_audit_package
from intentforge.review import ReviewEvaluationError, evaluate_assurance_case, get_review_policy
from intentforge.review.schema import ReviewPolicy
from tests.review_test_helpers import edit_case, full_case, rejection_case, standard_case, static_case


@pytest.mark.parametrize(
    ("case_factory", "policy_id", "expected"),
    [
        (lambda: standard_case(), "intentforge_standard_design_review_v1", "accepted_within_declared_scope"),
        (lambda: standard_case("l_bracket"), "intentforge_standard_design_review_v1", "accepted_within_declared_scope"),
        (lambda: standard_case(partial=True), "intentforge_standard_design_review_v1", "accepted_with_conditions"),
        (lambda: standard_case("l_bracket", partial=True), "intentforge_standard_design_review_v1", "manual_review_required"),
        (rejection_case, "intentforge_safe_rejection_review_v1", "accepted_within_declared_scope"),
        (edit_case, "intentforge_edit_review_v1", "accepted_within_declared_scope"),
    ],
)
def test_fixture_decisions(case_factory, policy_id: str, expected: str) -> None:
    pytest.importorskip("cadquery")
    decision = evaluate_assurance_case(get_review_policy(policy_id), case_factory())
    assert decision.decision_status == expected


def _single_check_policy(severity: str, *, claim_type: str | None = None) -> ReviewPolicy:
    base = get_review_policy("intentforge_static_review_v1").model_dump(mode="json", serialize_as_any=True)
    if claim_type:
        check = next(item for item in base["checks"] if item["check_type"] == "required_claim_status")
        check["parameters"] = {"claim_types": [claim_type], "allowed_statuses": ["supported"]}
    else:
        check = next(item for item in base["checks"] if item["check_type"] == "overall_assurance_status_allowed")
        check["parameters"] = {"allowed_statuses": ["assurance_complete"]}
    check["check_id"] = f"single_{severity}_check"
    check["severity"] = severity
    check["content_id"] = ""
    base["checks"] = [check]
    base["policy_id"] = f"single_{severity}_policy"
    base["content_id"] = ""
    return ReviewPolicy.model_validate(base)


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        ("blocking", "rejected_by_policy"),
        ("manual_review", "manual_review_required"),
        ("conditional", "accepted_with_conditions"),
        ("warning", "accepted_within_declared_scope"),
        ("informational", "accepted_within_declared_scope"),
    ],
)
def test_decision_precedence_for_failed_checks(severity: str, expected: str) -> None:
    assert evaluate_assurance_case(_single_check_policy(severity), static_case()).decision_status == expected


def test_unresolved_required_blocking_check_precedes_failure() -> None:
    policy = _single_check_policy("blocking", claim_type="geometry_generated")
    assert evaluate_assurance_case(policy, static_case()).decision_status == "unresolved"


def test_full_policy_requires_actual_package_and_artifact_integrity(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    case = full_case()
    package = build_audit_package(case, tmp_path / "package")
    decision = evaluate_assurance_case(
        get_review_policy("intentforge_full_design_review_v1"), case, package["validation"],
    )
    assert decision.decision_status == "accepted_within_declared_scope"


def test_policy_subject_mismatch_is_a_structured_error() -> None:
    with pytest.raises(ReviewEvaluationError, match="expects safe_rejection"):
        evaluate_assurance_case(get_review_policy("intentforge_safe_rejection_review_v1"), static_case())
