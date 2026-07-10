from intentforge.knowledge.reasoning.benchmark import run_reasoning_benchmark
from intentforge.knowledge.reasoning.engine import DEFAULT_REASONING_LIMITATIONS
from reasoning_test_helpers import reasoning_report
from pathlib import Path


def test_engine_builds_reasoning_report() -> None:
    report = reasoning_report(["hole_edge_margin_001"])

    assert report.report_id.startswith("reasoning_")
    assert report.reasoning_version == "1.0"
    assert report.summary["findings_analyzed"] == 1
    assert report.limitations == DEFAULT_REASONING_LIMITATIONS


def test_engine_traceability_rule_ids() -> None:
    report = reasoning_report(["hole_edge_margin_001"])

    assert report.observations[0].rule_ids == ["hole_edge_margin_001"]
    assert report.recommendations[0].rule_ids


def test_reasoning_benchmark_passes() -> None:
    result = run_reasoning_benchmark()

    assert result["failed"] == 0
    assert result["total_cases"] == 10


def test_reasoning_core_has_no_cadquery_llm_eval_or_exec_dependency() -> None:
    reasoning_root = Path("src/intentforge/knowledge/reasoning")
    source = "\n".join(path.read_text(encoding="utf-8") for path in reasoning_root.glob("*.py"))

    assert "cadquery" not in source.lower()
    assert "LLMProvider" not in source
    assert "eval(" not in source
    assert "exec(" not in source
