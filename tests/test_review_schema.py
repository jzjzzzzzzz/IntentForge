import pytest
from pydantic import ValidationError

from intentforge.review import load_review_policies
from intentforge.review.schema import PolicyCheck, ReviewPolicy


def test_packaged_policies_are_typed_and_deterministic() -> None:
    first = load_review_policies()
    second = load_review_policies()
    assert [item.policy_id for item in first] == sorted(item.policy_id for item in first)
    assert [item.content_id for item in first] == [item.content_id for item in second]
    assert all(item.to_json() == ReviewPolicy.model_validate_json(item.to_json()).to_json() for item in first)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("subject_type", "licensed_approval"),
        ("policy_scope", "arbitrary_code"),
        ("applicable_families", ["gear"]),
        ("applicable_operations", ["shell_command"]),
        ("required_assurance_profiles", ["certified"]),
    ],
)
def test_unknown_policy_enums_are_rejected(field: str, value) -> None:
    data = load_review_policies()[0].model_dump(mode="json", serialize_as_any=True)
    data[field] = value
    data["content_id"] = ""
    with pytest.raises(ValidationError):
        ReviewPolicy.model_validate(data)


def test_unknown_check_type_and_severity_are_rejected() -> None:
    check = load_review_policies()[0].checks[0].model_dump(mode="json", serialize_as_any=True)
    check["check_type"] = "python_expression"
    check["content_id"] = ""
    with pytest.raises(ValidationError):
        PolicyCheck.model_validate(check)
    check = load_review_policies()[0].checks[0].model_dump(mode="json", serialize_as_any=True)
    check["severity"] = "guaranteed_safe"
    check["content_id"] = ""
    with pytest.raises(ValidationError):
        PolicyCheck.model_validate(check)


@pytest.mark.parametrize("field", ["python", "command", "module", "callable", "field_path"])
def test_executable_or_arbitrary_check_parameters_are_rejected(field: str) -> None:
    check = load_review_policies()[0].checks[0].model_dump(mode="json", serialize_as_any=True)
    check["parameters"][field] = "case.claims == []"
    check["content_id"] = ""
    with pytest.raises(ValidationError):
        PolicyCheck.model_validate(check)
