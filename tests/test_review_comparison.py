from intentforge.review import compare_review_decisions, evaluate_assurance_case, get_review_policy
from tests.review_test_helpers import static_case


def test_identical_decisions_compare_equal_deterministically() -> None:
    decision = evaluate_assurance_case(get_review_policy("intentforge_static_review_v1"), static_case())
    first = compare_review_decisions(decision, decision)
    second = compare_review_decisions(decision, decision)
    assert first == second
    assert first["identical"]


def test_policy_change_is_reported() -> None:
    case = static_case()
    static = evaluate_assurance_case(get_review_policy("intentforge_static_review_v1"), case)
    changed = static.model_copy(update={"policy_version": "1.1"})
    result = compare_review_decisions(static, changed)
    assert not result["identical"]
    assert "policy" in result["changed_fields"]
