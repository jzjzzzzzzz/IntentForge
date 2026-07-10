import pytest

from intentforge.knowledge.reasoning.verification import (
    ReasoningVerificationError,
    load_golden_cases,
    run_golden_case,
    run_reasoning_verification,
    validate_golden_cases,
)


def test_golden_cases_load() -> None:
    cases = load_golden_cases()

    assert len(cases) == 10
    assert all(case["id"] for case in cases)
    assert all(case["expected_report_id"].startswith("reasoning_") for case in cases)


def test_duplicate_golden_case_ids_rejected() -> None:
    case = load_golden_cases()[0]

    with pytest.raises(ReasoningVerificationError, match="duplicate"):
        validate_golden_cases([case, dict(case)])


def test_golden_case_report_id_matches_expected() -> None:
    case = load_golden_cases()[1]
    result = run_golden_case(case)

    assert result["passed"] is True
    assert result["report_id"] == case["expected_report_id"]
    assert result["deterministic_report_id"] is True


def test_reasoning_verification_passes_all_golden_cases() -> None:
    result = run_reasoning_verification()

    assert result["total_cases"] == 10
    assert result["failed"] == 0
    assert result["pass_rate"] == 1.0
    assert result["report_id_mismatch_count"] == 0
