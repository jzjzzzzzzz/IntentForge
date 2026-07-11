from intentforge.review import evaluate_assurance_case, get_review_policy, validate_review_decision
from tests.review_test_helpers import static_case


def test_decision_validates_and_serializes() -> None:
    case = static_case()
    policy = get_review_policy("intentforge_static_review_v1")
    decision = evaluate_assurance_case(policy, case)
    result = validate_review_decision(decision, policy=policy, assurance_case=case)
    assert result.passed
    assert decision.__class__.model_validate_json(decision.to_json()) == decision


def test_runtime_metadata_request_id_and_timestamp_do_not_change_decision_identity() -> None:
    case = static_case()
    policy = get_review_policy("intentforge_static_review_v1")
    first = evaluate_assurance_case(policy, case, runtime_metadata={"timestamp": "first", "request_id": "one"})
    second = evaluate_assurance_case(policy, case, runtime_metadata={"timestamp": "second", "request_id": "two"})
    assert first.decision_id == second.decision_id
    assert first.content_id == second.content_id


def test_repeated_evaluation_has_stable_finding_and_condition_order() -> None:
    case = static_case()
    policy = get_review_policy("intentforge_static_review_v1")
    first = evaluate_assurance_case(policy, case)
    second = evaluate_assurance_case(policy, case)
    assert [item.finding_id for item in first.findings] == [item.finding_id for item in second.findings]
    assert [item.condition_id for item in first.conditions] == [item.condition_id for item in second.conditions]
