from intentforge.assurance import build_assurance_from_prompt, compare_assurance_cases


def test_identical_case_comparison() -> None:
    case = build_assurance_from_prompt(profile="static")
    result = compare_assurance_cases(case, case)
    assert result["identical"] is True
    assert result["changed_fields"] == []


def test_structured_change_is_reported() -> None:
    first = build_assurance_from_prompt(profile="static")
    second = build_assurance_from_prompt("Make a wall-mounted bracket 140 mm wide.", profile="static")
    result = compare_assurance_cases(first, second)
    assert not result["identical"]
    assert "structured_intent" in result["changed_fields"]
