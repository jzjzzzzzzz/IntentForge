from intentforge.knowledge import RuleRegistry
from intentforge.knowledge.reasoning.benchmark import run_reasoning_benchmark
from intentforge.knowledge.reasoning.verification import run_reasoning_verification


def test_reasoning_golden_cases_remain_stable_with_packs() -> None:
    result = run_reasoning_verification(rule_registry=RuleRegistry.load())

    assert result["total_cases"] == 10
    assert result["passed"] == 10
    assert result["failed"] == 0
    assert result["contradiction_count"] == 0
    assert result["applicability_error_count"] == 0
    assert result["nondeterministic_report_count"] == 0
    assert result["report_id_mismatch_count"] == 0


def test_reasoning_benchmark_remains_ten_of_ten() -> None:
    result = run_reasoning_benchmark(rule_registry=RuleRegistry.load())

    assert result["total_cases"] == 10
    assert result["passed"] == 10
    assert result["failed"] == 0
    assert result["pass_rate"] == 1.0
