import pytest

from intentforge.review import evaluate_assurance_case, get_review_policy
from intentforge.review.checks import evaluate_policy_check
from tests.review_test_helpers import edit_case, rejection_case, standard_case, static_case


def _check(policy_id: str, check_type: str):
    return next(item for item in get_review_policy(policy_id).checks if item.check_type == check_type)


def test_required_claim_and_evidence_checks_pass_static_case() -> None:
    case = static_case()
    for check_type in ("required_claim_status", "required_evidence_status"):
        result = evaluate_policy_check(_check("intentforge_static_review_v1", check_type), case)
        assert result.status == "passed"


def test_runtime_validation_check_passes_standard_case() -> None:
    pytest.importorskip("cadquery")
    result = evaluate_policy_check(
        _check("intentforge_standard_design_review_v1", "required_validation_status"),
        standard_case(),
    )
    assert result.status == "passed"
    assert len(result.validation_ids) == 3


def test_requested_partial_feature_check_is_not_applicable_then_fails() -> None:
    pytest.importorskip("cadquery")
    check = _check("intentforge_standard_design_review_v1", "limitation_requires_manual_review")
    assert evaluate_policy_check(check, standard_case()).status == "not_applicable"
    partial = evaluate_policy_check(check, standard_case(partial=True))
    assert partial.status == "failed"
    assert partial.limitation_ids


def test_safe_rejection_checks_structured_error_boundary_and_no_cad() -> None:
    case = rejection_case()
    policy = get_review_policy("intentforge_safe_rejection_review_v1")
    assert evaluate_policy_check(next(x for x in policy.checks if x.check_type == "safe_rejection_verified"), case).status == "passed"
    assert evaluate_policy_check(next(x for x in policy.checks if x.check_type == "no_cad_artifact_on_rejection"), case).status == "passed"


def test_edit_preservation_check_uses_change_and_preservation_trace() -> None:
    pytest.importorskip("cadquery")
    case = edit_case()
    check = _check("intentforge_edit_review_v1", "edit_intent_preservation_required")
    result = evaluate_policy_check(check, case)
    assert result.status == "passed"
    assert result.observed_value["changed_parameter_count"] > 0
    assert result.observed_value["preserved_parameter_count"] > 0
