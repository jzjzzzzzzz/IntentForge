import pytest
from pydantic import ValidationError

from intentforge.assurance import build_assurance_from_prompt
from intentforge.assurance.schema import AssuranceCase


def test_valid_assurance_case_serializes_deterministically() -> None:
    first = build_assurance_from_prompt(profile="static")
    second = build_assurance_from_prompt(profile="static")
    assert AssuranceCase.model_validate_json(first.to_json()).assurance_case_id == first.assurance_case_id
    assert first.assurance_case_id == second.assurance_case_id


def test_unknown_claim_type_and_status_rejected() -> None:
    case = build_assurance_from_prompt(profile="static").model_dump(mode="json")
    case["claims"][0]["claim_type"] = "certified_safe"
    with pytest.raises(ValidationError):
        AssuranceCase.model_validate(case)
    case = build_assurance_from_prompt(profile="static").model_dump(mode="json")
    case["claims"][0]["status"] = "probably_ok"
    with pytest.raises(ValidationError):
        AssuranceCase.model_validate(case)


def test_runtime_metadata_excluded_from_identity() -> None:
    case = build_assurance_from_prompt(profile="static")
    changed = case.model_copy(update={"runtime_metadata": {"timestamp": "later"}})
    assert case.deterministic_payload() == changed.deterministic_payload()
