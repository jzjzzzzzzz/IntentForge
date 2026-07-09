"""Adversarial rejection harness for unsupported and unsafe CAD requests."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

from intentforge.generator.cadquery_generator import CadQueryUnavailableError
from intentforge.output_manager import create_run_context, json_safe_paths
from intentforge.parser import UnsupportedEditError, UnsupportedObjectError
from intentforge.workflows import (
    edit_parse_apply_workflow,
    edit_parse_workflow,
    parse_build_workflow,
    parse_prompt_workflow,
)

SUPPORTED_MODES = {"parse", "parse_build", "edit_parse", "edit_parse_apply"}
FAILURE_TYPES = (
    "unexpected_acceptance",
    "cad_exported_on_rejection",
    "missing_error_message",
    "wrong_error_message",
    "unexpected_exception",
)


def _default_case_path() -> Path:
    return Path(__file__).with_name("adversarial_prompts.json")


def load_adversarial_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load adversarial rejection cases from JSON."""

    case_path = Path(path) if path is not None else _default_case_path()
    cases = json.loads(case_path.read_text(encoding="utf-8"))
    validate_adversarial_cases(cases)
    return cases


def validate_adversarial_cases(cases: list[dict[str, Any]]) -> None:
    """Validate required case fields and duplicate identifiers."""

    if not isinstance(cases, list):
        raise ValueError("adversarial case file must contain a list")
    seen: set[str] = set()
    duplicates: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each adversarial case must be an object")
        for key in ("id", "category", "mode", "input"):
            if not case.get(key):
                raise ValueError(f"adversarial case missing {key}")
        if case["id"] in seen:
            duplicates.append(str(case["id"]))
        seen.add(str(case["id"]))
        if case["mode"] not in SUPPORTED_MODES:
            raise ValueError(f"unsupported adversarial mode: {case['mode']}")
        if case.get("expected_rejected") is not True:
            raise ValueError(f"adversarial case {case['id']} must expect rejection")
    if duplicates:
        raise ValueError(f"duplicate adversarial ids: {', '.join(sorted(set(duplicates)))}")


def _write_json(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _cad_files(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted(str(file) for file in path.rglob("*") if file.suffix.lower() in {".step", ".stl"})


def _result_message(result: dict[str, Any]) -> str:
    message = result.get("message") or result.get("error") or ""
    if message:
        return str(message)
    edit_report = result.get("edit_report")
    if isinstance(edit_report, dict):
        return str(edit_report.get("human_readable_explanation") or edit_report.get("validation_summary") or "")
    validation_report = result.get("validation_report")
    if isinstance(validation_report, dict):
        return str(validation_report.get("summary") or "")
    return ""


def _is_accepted(result: dict[str, Any]) -> bool:
    if result.get("accepted") is True:
        return True
    return bool(result.get("ok"))


def _exception_result(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "accepted": False,
        "error_type": type(exc).__name__,
        "message": str(exc),
        "cad_exported": False,
    }


def _run_case_workflow(case: dict[str, Any], case_output: Path) -> dict[str, Any]:
    mode = case["mode"]
    text = case["input"]
    if mode == "parse":
        return parse_prompt_workflow(text, case_output, write_outputs=True)
    if mode == "parse_build":
        return parse_build_workflow(text, case_output)
    if mode == "edit_parse":
        return edit_parse_workflow(text, case_output, write_outputs=True)
    if mode == "edit_parse_apply":
        return edit_parse_apply_workflow(case.get("target", "bracket"), text, case_output)
    raise ValueError(f"unsupported adversarial mode: {mode}")


def _classification(
    case: dict[str, Any],
    result: dict[str, Any],
    cad_files: list[str],
    unexpected_exception: bool,
) -> tuple[bool, str, str]:
    if unexpected_exception:
        return False, "unexpected_exception", _result_message(result)
    if _is_accepted(result):
        return False, "unexpected_acceptance", "case was accepted but expected rejection"
    if not case.get("expected_cad_exported", False) and (cad_files or result.get("cad_exported") is True):
        return False, "cad_exported_on_rejection", "rejected case exported CAD"
    message = _result_message(result)
    if not message:
        return False, "missing_error_message", "rejection did not include an error message"
    expected = case.get("expected_error_contains")
    if expected and str(expected) not in message:
        return False, "wrong_error_message", f"expected error containing {expected!r}, actual={message!r}"
    return True, "passed", ""


def run_adversarial_case(case: dict[str, Any], output_root: str | Path) -> dict[str, Any]:
    """Run one adversarial rejection case and compare it against expectations."""

    case_output = Path(output_root) / str(case["id"])
    case_output.mkdir(parents=True, exist_ok=True)
    unexpected_exception = False
    try:
        result = _run_case_workflow(case, case_output)
    except (UnsupportedObjectError, UnsupportedEditError) as exc:
        result = _exception_result(exc)
    except CadQueryUnavailableError as exc:
        result = _exception_result(exc)
        unexpected_exception = True
    except Exception as exc:  # pragma: no cover - defensive for environment-specific failures
        result = _exception_result(exc)
        unexpected_exception = True

    cad_files = _cad_files(case_output)
    passed, classification, reason = _classification(case, result, cad_files, unexpected_exception)
    case_result = {
        "id": case["id"],
        "category": case["category"],
        "mode": case["mode"],
        "input": case["input"],
        "passed": passed,
        "classification": classification,
        "failure_reason": reason,
        "expected_rejected": case.get("expected_rejected", True),
        "expected_error_contains": case.get("expected_error_contains"),
        "expected_cad_exported": case.get("expected_cad_exported", False),
        "actual_ok": bool(result.get("ok")),
        "actual_accepted": result.get("accepted"),
        "actual_message": _result_message(result),
        "cad_exported": bool(cad_files or result.get("cad_exported") is True),
        "cad_files": cad_files,
        "output_dir": str(case_output),
        "workflow_result": result,
    }
    _write_json(case_result, case_output / "case_result.json")
    return case_result


def _summary_text(report: dict[str, Any]) -> str:
    lines = [
        f"Adversarial rejection run: {report['run_id']}",
        f"Total cases: {report['total_cases']}",
        f"Passed: {report['passed']}",
        f"Failed: {report['failed']}",
        f"Rejection success rate: {report['rejection_success_rate']:.4f}",
        "Categories:",
    ]
    for category, counts in report["categories"].items():
        lines.append(f"  - {category}: passed {counts['passed']}, failed {counts['failed']}, total {counts['total']}")
    lines.append("Failure types:")
    for failure_type, count in report["failure_types"].items():
        lines.append(f"  - {failure_type}: {count}")
    if report["failed_cases"]:
        lines.append("Failed case IDs:")
        for case in report["failed_cases"]:
            lines.append(f"  - {case['id']}: {case['classification']} - {case['failure_reason']}")
    else:
        lines.append("Failed case IDs: none")
    return "\n".join(lines) + "\n"


def run_adversarial_harness(
    output_root: str | Path,
    max_cases: int | None = None,
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run all adversarial rejection cases and write latest and persistent reports."""

    output_path = Path(output_root)
    harness_root = output_path / "harness"
    run_context = create_run_context("adversarial rejection harness", harness_root, "adversarial_runs")
    cases = load_adversarial_cases(config_path)
    if max_cases is not None:
        cases = cases[: max(0, max_cases)]

    case_results = [
        run_adversarial_case(case, run_context.run_dir / "cases")
        for case in cases
    ]
    passed_cases = [case for case in case_results if case["passed"]]
    failed_cases = [case for case in case_results if not case["passed"]]

    categories: dict[str, dict[str, int]] = {}
    for category in sorted({case["category"] for case in case_results}):
        category_cases = [case for case in case_results if case["category"] == category]
        categories[category] = {
            "total": len(category_cases),
            "passed": sum(1 for case in category_cases if case["passed"]),
            "failed": sum(1 for case in category_cases if not case["passed"]),
        }

    failure_counts = Counter(case["classification"] for case in failed_cases if case["classification"] in FAILURE_TYPES)
    failure_types = {failure_type: failure_counts.get(failure_type, 0) for failure_type in FAILURE_TYPES}

    latest_report_path = harness_root / "adversarial_report.json"
    latest_summary_path = harness_root / "adversarial_summary.txt"
    persistent_report_path = run_context.run_dir / "adversarial_report.json"
    persistent_summary_path = run_context.run_dir / "adversarial_summary.txt"
    passed_cases_path = run_context.run_dir / "passed_cases.json"
    failed_cases_path = run_context.run_dir / "failed_cases.json"
    output_paths = {
        "latest_report": latest_report_path,
        "latest_summary": latest_summary_path,
        "persistent_report": persistent_report_path,
        "persistent_summary": persistent_summary_path,
        "passed_cases": passed_cases_path,
        "failed_cases": failed_cases_path,
    }
    report = {
        "run_id": run_context.run_id,
        "total_cases": len(case_results),
        "passed": len(passed_cases),
        "failed": len(failed_cases),
        "rejection_success_rate": len(passed_cases) / len(case_results) if case_results else 0.0,
        "categories": categories,
        "failure_types": failure_types,
        "case_results": case_results,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "output_paths": json_safe_paths(output_paths),
    }
    summary = _summary_text(report)
    _write_json(report, latest_report_path)
    _write_text(summary, latest_summary_path)
    _write_json(report, persistent_report_path)
    _write_text(summary, persistent_summary_path)
    _write_json(passed_cases, passed_cases_path)
    _write_json(failed_cases, failed_cases_path)
    return {
        **report,
        "report_path": str(latest_report_path),
        "summary_path": str(latest_summary_path),
        "persistent_output_dir": str(run_context.run_dir),
        "summary": summary,
    }
