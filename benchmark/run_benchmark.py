"""Deterministic benchmark runner for IntentForge."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from intentforge.generator.cadquery_generator import CadQueryUnavailableError
from intentforge.output_manager import create_run_context, write_run_metadata
from intentforge.parser import UnsupportedObjectError, parse_prompt
from intentforge.workflows import (
    default_output_root,
    edit_parse_apply_workflow,
    parse_build_workflow,
)

BENCHMARK_DIR = Path(__file__).resolve().parent
PROMPT_FILES = {
    "clean": BENCHMARK_DIR / "prompts" / "clean_prompts.json",
    "defaults": BENCHMARK_DIR / "prompts" / "default_prompts.json",
    "optional_features": BENCHMARK_DIR / "prompts" / "optional_feature_prompts.json",
    "hole_patterns": BENCHMARK_DIR / "prompts" / "hole_pattern_prompts.json",
    "rejections": BENCHMARK_DIR / "prompts" / "rejection_prompts.json",
    "edits": BENCHMARK_DIR / "prompts" / "edit_prompts.json",
}
EXPECTED_FEATURES_PATH = BENCHMARK_DIR / "expected" / "expected_features.json"
EXPECTED_REJECTIONS_PATH = BENCHMARK_DIR / "expected" / "expected_rejections.json"


@dataclass(frozen=True)
class BenchmarkContext:
    run_id: str
    run_dir: Path
    benchmark_root: Path
    created_at: datetime
    latest_report_path: Path
    latest_summary_path: Path
    persistent_report_path: Path
    persistent_summary_path: Path
    failed_cases_path: Path
    passed_cases_path: Path


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_expected_features() -> dict[str, Any]:
    """Load canonical feature expectations used by the benchmark runner."""

    return _load_json(EXPECTED_FEATURES_PATH)


def load_expected_rejections() -> dict[str, Any]:
    """Load canonical rejection strings used by the benchmark runner."""

    return _load_json(EXPECTED_REJECTIONS_PATH)


def load_benchmark_cases(benchmark_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load all benchmark cases from the prompt JSON files."""

    base_dir = benchmark_dir or BENCHMARK_DIR
    cases: list[dict[str, Any]] = []
    for category, path in PROMPT_FILES.items():
        category_path = base_dir / path.relative_to(BENCHMARK_DIR)
        for case in _load_json(category_path):
            case = dict(case)
            case["category"] = category
            case["_source_file"] = str(category_path)
            cases.append(case)
    return cases


def validate_benchmark_cases(cases: list[dict[str, Any]]) -> None:
    """Validate case identifiers and detect duplicates."""

    seen: set[str] = set()
    duplicates: list[str] = []
    for case in cases:
        if "id" not in case or not case["id"]:
            raise ValueError("benchmark case missing id")
        if "type" not in case or not case["type"]:
            raise ValueError(f"benchmark case {case['id']} missing type")
        case_id = str(case["id"])
        if case_id in seen:
            duplicates.append(case_id)
        seen.add(case_id)
    if duplicates:
        raise ValueError(f"duplicate benchmark ids: {', '.join(sorted(set(duplicates)))}")


def _benchmark_root(output_root: str | Path | None = None) -> Path:
    root = Path(output_root) if output_root is not None else default_output_root()
    benchmark_root = root / "benchmark"
    benchmark_root.mkdir(parents=True, exist_ok=True)
    return benchmark_root


def _make_context(output_root: str | Path | None = None) -> BenchmarkContext:
    benchmark_root = _benchmark_root(output_root)
    run_context = create_run_context("benchmark", benchmark_root, "runs")
    latest_report_path = benchmark_root / "benchmark_report.json"
    latest_summary_path = benchmark_root / "benchmark_summary.txt"
    persistent_report_path = run_context.run_dir / "benchmark_report.json"
    persistent_summary_path = run_context.run_dir / "benchmark_summary.txt"
    failed_cases_path = run_context.run_dir / "failed_cases.json"
    passed_cases_path = run_context.run_dir / "passed_cases.json"
    return BenchmarkContext(
        run_id=run_context.run_id,
        run_dir=run_context.run_dir,
        benchmark_root=benchmark_root,
        created_at=run_context.created_at,
        latest_report_path=latest_report_path,
        latest_summary_path=latest_summary_path,
        persistent_report_path=persistent_report_path,
        persistent_summary_path=persistent_summary_path,
        failed_cases_path=failed_cases_path,
        passed_cases_path=passed_cases_path,
    )


def _case_output_root(context: BenchmarkContext, case_id: str) -> Path:
    return context.run_dir / "cases" / case_id


def _set_from_sequence(values: Any) -> set[str]:
    if not values:
        return set()
    return {str(value) for value in values}


def _expected_error_contains(case: dict[str, Any], expected_rejections: dict[str, Any]) -> str | None:
    if "expected_error_contains" in case:
        return str(case["expected_error_contains"])
    category = case.get("category")
    if category == "rejections":
        return expected_rejections.get("unsupported_object")
    return None


def _result_paths(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in result.items()
        if key.endswith("_path") or key.endswith("_outputs") or key == "persistent_output_dir"
    }


def _case_pass(
    case: dict[str, Any],
    actual: dict[str, Any],
    expected_features: dict[str, Any],
    expected_rejections: dict[str, Any],
) -> tuple[bool, str]:
    expected_ok = case.get("expected_ok")
    if expected_ok is not None and bool(actual.get("ok")) != bool(expected_ok):
        return False, f"expected ok={expected_ok}, actual ok={actual.get('ok')}"

    if expected_ok is False:
        expected_error = _expected_error_contains(case, expected_rejections)
        message = str(actual.get("message") or actual.get("error") or "")
        if expected_error and expected_error not in message:
            return False, f"expected error containing {expected_error!r}, actual={message!r}"
        return True, "rejection matched expected outcome"

    if case["type"] == "parse_build":
        if "expected_validation_valid" in case and bool(actual.get("validation_valid")) != bool(case["expected_validation_valid"]):
            return False, (
                f"expected validation_valid={case['expected_validation_valid']}, "
                f"actual={actual.get('validation_valid')}"
            )
        if "expected_active_features" in case and _set_from_sequence(case.get("expected_active_features")) != _set_from_sequence(actual.get("active_features")):
            expected_active = sorted(_set_from_sequence(case.get("expected_active_features")))
            actual_active = sorted(_set_from_sequence(actual.get("active_features")))
            return False, f"active features mismatch: expected {sorted(expected_active)}, actual {sorted(_set_from_sequence(actual.get('active_features')))}"
        if "expected_omitted_features" in case and _set_from_sequence(case.get("expected_omitted_features")) != _set_from_sequence(actual.get("omitted_features")):
            expected_omitted = sorted(_set_from_sequence(case.get("expected_omitted_features")))
            actual_omitted = sorted(_set_from_sequence(actual.get("omitted_features")))
            return False, f"omitted features mismatch: expected {sorted(expected_omitted)}, actual {sorted(_set_from_sequence(actual.get('omitted_features')))}"
        expected_pattern = case.get("expected_hole_pattern")
        if expected_pattern is not None:
            actual_pattern = (
                actual.get("parameters", {})
                .get("metadata", {})
                .get("feature_flags", {})
                .get("mounting_holes", {})
                .get("pattern")
            )
            if actual_pattern != expected_pattern:
                return False, f"expected hole pattern {expected_pattern!r}, actual {actual_pattern!r}"
        return True, "parse-build benchmark case passed"

    if case["type"] == "edit_parse_apply":
        if "expected_accepted" in case and bool(actual.get("accepted")) != bool(case["expected_accepted"]):
            return False, f"expected accepted={case['expected_accepted']}, actual={actual.get('accepted')}"
        if "expected_validation_valid" in case and bool(actual.get("validation_valid")) != bool(case["expected_validation_valid"]):
            return False, (
                f"expected validation_valid={case['expected_validation_valid']}, "
                f"actual={actual.get('validation_valid')}"
            )
        if case.get("expected_accepted"):
            edit_report = actual.get("edit_report") or {}
            changed = {item.get("parameter") for item in edit_report.get("changed_parameters", [])}
            preserved = {item.get("parameter") for item in edit_report.get("preserved_parameters", [])}
            if "expected_changed_parameters" in case:
                expected_changed = _set_from_sequence(case.get("expected_changed_parameters"))
                if not expected_changed.issubset(changed):
                    return False, f"changed parameters mismatch: expected at least {sorted(expected_changed)}, actual {sorted(changed)}"
            if "expected_preserved_parameters" in case:
                expected_preserved = _set_from_sequence(case.get("expected_preserved_parameters"))
                if not expected_preserved.issubset(preserved):
                    return False, f"preserved parameters mismatch: expected at least {sorted(expected_preserved)}, actual {sorted(preserved)}"
        else:
            expected_error = _expected_error_contains(case, expected_rejections)
            message = str(actual.get("message") or actual.get("error") or "")
            if expected_error and expected_error not in message:
                return False, f"expected error containing {expected_error!r}, actual={message!r}"
            if actual.get("cad_exported"):
                return False, "rejected edit exported CAD"
        return True, "edit benchmark case passed"

    if case["type"] == "parse":
        # parse cases in this benchmark set are rejection checks
        expected_error = _expected_error_contains(case, expected_rejections)
        message = str(actual.get("message") or actual.get("error") or "")
        if expected_error and expected_error not in message:
            return False, f"expected error containing {expected_error!r}, actual={message!r}"
        return True, "parse rejection matched expected outcome"

    return False, f"unsupported benchmark case type: {case['type']}"


def _run_case(
    case: dict[str, Any],
    context: BenchmarkContext,
    expected_features: dict[str, Any],
    expected_rejections: dict[str, Any],
) -> dict[str, Any]:
    case_output_root = _case_output_root(context, case["id"])
    case_output_root.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any]

    try:
        if case["type"] == "parse_build":
            result = parse_build_workflow(case["prompt"], case_output_root)
        elif case["type"] == "edit_parse_apply":
            result = edit_parse_apply_workflow(case["target"], case["edit_text"], case_output_root)
        elif case["type"] == "parse":
            try:
                parsed = parse_prompt(case["prompt"])
            except Exception as exc:  # unsupported prompts are expected here
                result = {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            else:
                result = {
                    "ok": True,
                    "intent": parsed.intent.model_dump(mode="json"),
                    "parameters": parsed.parameter_table.model_dump(mode="json"),
                    "constraints": parsed.constraint_graph.model_dump(mode="json"),
                    "feature_plan": parsed.feature_plan.model_dump(mode="json"),
                    "warnings": parsed.warnings,
                    "assumptions": parsed.intent.assumptions,
                    "unknowns": parsed.intent.unknowns,
                }
        else:
            result = {
                "ok": False,
                "error_type": "ValueError",
                "message": f"unsupported benchmark case type: {case['type']}",
            }
    except (CadQueryUnavailableError, UnsupportedObjectError, ValueError) as exc:
        result = {
            "ok": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }

    passed, reason = _case_pass(case, result, expected_features, expected_rejections)
    case_result = {
        "id": case["id"],
        "category": case["category"],
        "type": case["type"],
        "passed": passed,
        "reason": reason,
        "expected": {key: value for key, value in case.items() if key.startswith("expected_")},
        "actual": result,
        "output_paths": _result_paths(result),
    }
    return case_result


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _build_summary(report: dict[str, Any]) -> str:
    lines = [
        f"Benchmark run: {report['run_id']}",
        f"Total cases: {report['total_cases']}",
        f"Passed: {report['passed']}",
        f"Failed: {report['failed']}",
        f"Pass rate: {report['pass_rate']:.4f}",
        "Categories:",
    ]
    for name, stats in report["categories"].items():
        lines.append(f"  - {name}: passed {stats['passed']}, failed {stats['failed']}")
    if report["failed_cases"]:
        lines.append("Failed case IDs:")
        for case in report["failed_cases"]:
            lines.append(f"  - {case['id']}")
    else:
        lines.append("Failed case IDs: none")
    return "\n".join(lines) + "\n"


def run_benchmark(
    output_root: str | Path | None = None,
    benchmark_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the benchmark suite and write report artifacts."""

    expected_features = load_expected_features()
    expected_rejections = load_expected_rejections()
    cases = load_benchmark_cases(benchmark_dir)
    validate_benchmark_cases(cases)

    context = _make_context(output_root)
    case_results = [_run_case(case, context, expected_features, expected_rejections) for case in cases]
    passed_cases = [case for case in case_results if case["passed"]]
    failed_cases = [case for case in case_results if not case["passed"]]
    total_cases = len(case_results)
    passed = len(passed_cases)
    failed = len(failed_cases)
    pass_rate = round(passed / total_cases, 4) if total_cases else 0.0

    category_names = ["clean", "defaults", "optional_features", "hole_patterns", "rejections", "edits"]
    categories: dict[str, dict[str, int]] = {
        name: {"passed": 0, "failed": 0} for name in category_names
    }
    for case in case_results:
        category = case["category"]
        if category not in categories:
            categories[category] = {"passed": 0, "failed": 0}
        categories[category]["passed" if case["passed"] else "failed"] += 1

    report = {
        "run_id": context.run_id,
        "total_cases": total_cases,
        "passed": passed,
        "failed": failed,
        "pass_rate": pass_rate,
        "categories": categories,
        "failed_cases": [
            {
                "id": case["id"],
                "reason": case["reason"],
                "expected": case["expected"],
                "actual": case["actual"],
            }
            for case in failed_cases
        ],
    }
    summary = _build_summary(report)

    write_run_metadata(
        {
            "run_id": context.run_id,
            "command_type": "benchmark",
            "created_at": context.created_at.isoformat(),
            "output_paths": {
                "latest_report_path": str(context.latest_report_path),
                "latest_summary_path": str(context.latest_summary_path),
                "persistent_report_path": str(context.persistent_report_path),
                "persistent_summary_path": str(context.persistent_summary_path),
            },
        },
        context.run_dir / "run_metadata.json",
    )
    _write_text(context.latest_report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write_text(context.persistent_report_path, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write_text(context.latest_summary_path, summary)
    _write_text(context.persistent_summary_path, summary)
    _write_text(context.failed_cases_path, json.dumps(failed_cases, indent=2, sort_keys=True) + "\n")
    _write_text(context.passed_cases_path, json.dumps(passed_cases, indent=2, sort_keys=True) + "\n")
    return {
        **report,
        "summary": summary,
        "report_path": str(context.latest_report_path),
        "summary_path": str(context.latest_summary_path),
        "persistent_report_path": str(context.persistent_report_path),
        "persistent_summary_path": str(context.persistent_summary_path),
        "failed_cases_path": str(context.failed_cases_path),
        "passed_cases_path": str(context.passed_cases_path),
        "run_dir": str(context.run_dir),
        "case_results": case_results,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the benchmark runner."""

    result = run_benchmark()
    print(result["summary"], end="")
    print(f"Latest report: {result['report_path']}")
    print(f"Persistent report: {result['persistent_report_path']}")
    print(f"Failed cases: {', '.join(case['id'] for case in result['failed_cases']) if result['failed_cases'] else 'none'}")
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
