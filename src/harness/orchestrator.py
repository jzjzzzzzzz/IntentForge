"""Technical harness orchestrator and quality gates."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import importlib.util
import json
from pathlib import Path
from typing import Any

import yaml

from benchmark.run_benchmark import run_benchmark
from harness.adversarial import run_adversarial_harness
from harness.edits import run_edit_preservation_harness
from harness.sweeps import run_parametric_sweep
from harness.topology import (
    build_volume_delta_report,
    inspect_shape,
    recognize_features,
    write_feature_recognition_report,
    write_feature_recognition_summary,
    write_shape_inspection_report,
)
from intentforge.generator.cadquery_generator import (
    CadQueryUnavailableError,
    build_l_bracket,
    build_wall_bracket,
)
from intentforge.output_manager import create_run_context, feature_state_names, json_safe_paths
from intentforge.paths import project_root as _intentforge_project_root
from intentforge.schemas import ParameterTable
from intentforge.knowledge import (
    RuleRegistry,
    build_design_metrics,
    build_engineering_reasoning_report,
    evaluate_parameter_table,
    make_knowledge_report,
)
from intentforge.knowledge.reasoning.benchmark import run_reasoning_benchmark

SUPPORTED_MODEL_FAMILIES = ("wall_mounted_bracket", "l_bracket")

QUALITY_GATES: dict[str, float | int] = {
    "benchmark_pass_rate_min": 0.95,
    "sweep_pass_rate_min": 0.95,
    "edit_preservation_rate_min": 0.95,
    "adversarial_rejection_success_rate_min": 1.0,
    "unexpected_failure_count_max": 0,
    "unsafe_acceptance_count_max": 0,
    "unexpected_exception_count_max": 0,
    "reasoning_generation_pass_rate_min": 1.0,
    "unknown_rule_reference_count_max": 0,
    "duplicate_recommendation_count_max": 0,
    "missing_limitation_count_max": 0,
}


def _project_root() -> Path:
    return _intentforge_project_root()


def _cadquery_available() -> bool:
    return importlib.util.find_spec("cadquery") is not None


def _require_cadquery() -> None:
    if not _cadquery_available():
        raise CadQueryUnavailableError(
            "CadQuery is required to run the technical harness because it builds, "
            "inspects, and validates real CAD models. Install it with: "
            "python -m pip install -e '.[cad]'"
        )


def _write_json(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _load_example_parameters(family: str) -> ParameterTable:
    filenames = {
        "wall_mounted_bracket": "bracket_params.yaml",
        "l_bracket": "l_bracket_params.yaml",
    }
    if family not in filenames:
        raise ValueError(f"Unsupported model family: {family}")
    path = _project_root() / "examples" / filenames[family]
    return ParameterTable.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _build_example_model(parameter_table: ParameterTable) -> Any:
    if parameter_table.family == "l_bracket":
        return build_l_bracket(parameter_table)
    if parameter_table.family == "wall_mounted_bracket":
        return build_wall_bracket(parameter_table)
    raise ValueError(f"Unsupported model family: {parameter_table.family}")


def _run_section(name: str, runner: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started_at = datetime.now().astimezone().isoformat()
    try:
        section = runner()
        return {
            "name": name,
            "passed": bool(section.get("passed", False)),
            "started_at": started_at,
            "completed_at": datetime.now().astimezone().isoformat(),
            **section,
        }
    except Exception as exc:  # pragma: no cover - exercised through integration failures
        return {
            "name": name,
            "passed": False,
            "started_at": started_at,
            "completed_at": datetime.now().astimezone().isoformat(),
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }


def _benchmark_section(output_root: Path) -> dict[str, Any]:
    result = run_benchmark(output_root=output_root)
    return {
        "passed": result["failed"] == 0,
        "run_id": result["run_id"],
        "total_cases": result["total_cases"],
        "passed_cases": result["passed"],
        "failed_cases": result["failed"],
        "pass_rate": result["pass_rate"],
        "families": result["families"],
        "categories": result["categories"],
        "report_path": result["report_path"],
        "summary_path": result["summary_path"],
        "persistent_output_dir": result["run_dir"],
    }


def _sweep_section(output_root: Path, *, quick: bool) -> dict[str, Any]:
    result = run_parametric_sweep(
        output_root,
        max_cases_per_family=10 if quick else 30,
        export_enabled=True,
    )
    return {
        "passed": result["failed"] == 0,
        "run_id": result["run_id"],
        "total_cases": result["total_cases"],
        "passed_cases": result["passed"],
        "failed_cases": result["failed"],
        "pass_rate": result["pass_rate"],
        "families": result["families"],
        "failure_types": result["failure_types"],
        "report_path": result["report_path"],
        "summary_path": result["summary_path"],
        "persistent_output_dir": result["persistent_output_dir"],
    }


def _edit_preservation_section(output_root: Path) -> dict[str, Any]:
    result = run_edit_preservation_harness(output_root, export_enabled=True)
    return {
        "passed": result["failed_chains"] == 0 and result["failed_steps"] == 0,
        "run_id": result["run_id"],
        "total_chains": result["total_chains"],
        "passed_chains": result["passed_chains"],
        "failed_chains": result["failed_chains"],
        "total_edit_steps": result["total_edit_steps"],
        "passed_steps": result["passed_steps"],
        "failed_steps": result["failed_steps"],
        "edit_preservation_rate": result["edit_preservation_rate"],
        "families": result["families"],
        "failure_types": result["failure_types"],
        "report_path": result["report_path"],
        "summary_path": result["summary_path"],
        "persistent_output_dir": result["persistent_output_dir"],
    }


def _adversarial_section(output_root: Path) -> dict[str, Any]:
    result = run_adversarial_harness(output_root)
    return {
        "passed": result["failed"] == 0,
        "run_id": result["run_id"],
        "total_cases": result["total_cases"],
        "passed_cases": result["passed"],
        "failed_cases": result["failed"],
        "rejection_success_rate": result["rejection_success_rate"],
        "categories": result["categories"],
        "failure_types": result["failure_types"],
        "report_path": result["report_path"],
        "summary_path": result["summary_path"],
        "persistent_output_dir": result["persistent_output_dir"],
    }


def _volume_delta_section(run_dir: Path) -> dict[str, Any]:
    volume_dir = run_dir / "volume_delta"
    reports: dict[str, dict[str, Any]] = {}
    failed_families: list[str] = []

    for family in SUPPORTED_MODEL_FAMILIES:
        parameter_table = _load_example_parameters(family)
        model = _build_example_model(parameter_table)
        active_features, omitted_features = feature_state_names(parameter_table)
        report_path = volume_dir / f"{family}_volume_delta_report.json"
        report = build_volume_delta_report(
            parameter_table,
            model,
            run_id=f"{run_dir.name}_{family}",
            active_features=active_features,
            omitted_features=omitted_features,
            output_paths={"persistent_report": str(report_path)},
        )
        _write_json(report, report_path)
        if not report["passed"]:
            failed_families.append(family)
        reports[family] = {
            "passed": report["passed"],
            "active_features": report["active_features"],
            "omitted_features": report["omitted_features"],
            "feature_volume_mm3": report["feature_volume_mm3"],
            "check_count": len(report["checks"]),
            "failed_checks": report["failed_checks"],
            "warnings": report["warnings"],
            "report_path": str(report_path),
        }

    return {
        "passed": not failed_families,
        "families": reports,
        "failed_families": failed_families,
    }


def _shape_inspection_section(run_dir: Path) -> dict[str, Any]:
    shape_dir = run_dir / "shape_inspection"
    reports: dict[str, dict[str, Any]] = {}
    failed_families: list[str] = []

    for family in SUPPORTED_MODEL_FAMILIES:
        parameter_table = _load_example_parameters(family)
        model = _build_example_model(parameter_table)
        report = inspect_shape(model, family=family)
        report_path = shape_dir / f"{family}_topology_report.json"
        write_shape_inspection_report(report, report_path)
        passed = (
            report.bounding_box_dimensions_mm is not None
            and report.volume_mm3 is not None
            and report.is_valid is not False
        )
        if not passed:
            failed_families.append(family)
        reports[family] = {
            "passed": passed,
            "bounding_box_dimensions_mm": report.bounding_box_dimensions_mm,
            "volume_mm3": report.volume_mm3,
            "solid_count": report.solid_count,
            "face_count": report.face_count,
            "edge_count": report.edge_count,
            "vertex_count": report.vertex_count,
            "is_valid": report.is_valid,
            "warning_count": len(report.warnings),
            "warnings": [warning.model_dump(mode="json") for warning in report.warnings],
            "report_path": str(report_path),
        }

    return {
        "passed": not failed_families,
        "families": reports,
        "failed_families": failed_families,
    }


def _feature_recognition_section(run_dir: Path) -> dict[str, Any]:
    recognition_dir = run_dir / "feature_recognition"
    reports: dict[str, dict[str, Any]] = {}
    warning_count = 0
    failed_families: list[str] = []

    for family in SUPPORTED_MODEL_FAMILIES:
        parameter_table = _load_example_parameters(family)
        model = _build_example_model(parameter_table)
        report = recognize_features(model, parameter_table)
        report_path = recognition_dir / f"{family}_feature_recognition_report.json"
        summary_path = recognition_dir / f"{family}_feature_recognition_summary.txt"
        write_feature_recognition_report(report, report_path)
        write_feature_recognition_summary(report, summary_path)
        warning_count += len(report.get("warnings", []) or [])
        if not report.get("passed", False):
            failed_families.append(family)
        reports[family] = {
            "passed": bool(report.get("passed", False)),
            "warning_count": len(report.get("warnings", []) or []),
            "recognized_features": report.get("recognized_features", {}),
            "topology_checks": report.get("topology_checks", {}),
            "report_path": str(report_path),
            "summary_path": str(summary_path),
        }

    pass_rate = (len(SUPPORTED_MODEL_FAMILIES) - len(failed_families)) / len(SUPPORTED_MODEL_FAMILIES)
    return {
        "passed": True,
        "warning_only": True,
        "pass_rate": pass_rate,
        "warning_count": warning_count,
        "families": reports,
        "failed_families": failed_families,
    }


def _reasoning_section(run_dir: Path) -> dict[str, Any]:
    reasoning_dir = run_dir / "engineering_reasoning"
    registry = RuleRegistry.load()
    known_rule_ids = {rule.id for rule in registry.rules}
    family_reports: dict[str, dict[str, Any]] = {}
    unknown_rule_reference_count = 0
    duplicate_recommendation_count = 0
    missing_limitation_count = 0
    failed_families: list[str] = []

    for family in SUPPORTED_MODEL_FAMILIES:
        parameter_table = _load_example_parameters(family)
        # Feature plan is not required for this lightweight reasoning check.
        findings = evaluate_parameter_table(parameter_table)
        knowledge_report = make_knowledge_report(findings, rules_checked=registry.count(), timestamp="2026-07-10T00:00:00+00:00")
        metrics = build_design_metrics(parameter_table)
        report = build_engineering_reasoning_report(
            model_family=family,
            knowledge_report=knowledge_report,
            rule_registry=registry,
            metrics=metrics,
            parameters={parameter.name: parameter.value for parameter in parameter_table.parameters},
            timestamp="2026-07-10T00:00:00+00:00",
        )
        repeat = build_engineering_reasoning_report(
            model_family=family,
            knowledge_report=knowledge_report,
            rule_registry=registry,
            metrics=metrics,
            parameters={parameter.name: parameter.value for parameter in parameter_table.parameters},
            timestamp="2026-07-10T00:00:00+00:00",
        )
        report_path = reasoning_dir / f"{family}_engineering_reasoning_report.json"
        _write_json(report.model_dump(mode="json"), report_path)

        referenced_rule_ids: set[str] = set()
        for collection_name in ("observations", "interactions", "conflicts", "recommendations"):
            collection = getattr(report, collection_name)
            for item in collection:
                referenced_rule_ids.update(getattr(item, "rule_ids", []))
        for tradeoff in report.tradeoffs:
            referenced_rule_ids.update(tradeoff.source_rule_ids)
        unknown = sorted(referenced_rule_ids - known_rule_ids)
        unknown_rule_reference_count += len(unknown)

        recommendation_ids = [recommendation.recommendation_id for recommendation in report.recommendations]
        duplicate_recommendation_count += len(recommendation_ids) - len(set(recommendation_ids))
        if not report.limitations:
            missing_limitation_count += 1
        missing_limitation_count += len([recommendation for recommendation in report.recommendations if not recommendation.limitations])

        passed = (
            report.report_id == repeat.report_id
            and not unknown
            and len(recommendation_ids) == len(set(recommendation_ids))
            and bool(report.limitations)
        )
        if not passed:
            failed_families.append(family)
        family_reports[family] = {
            "passed": passed,
            "report_id": report.report_id,
            "deterministic_report_id": report.report_id == repeat.report_id,
            "unknown_rule_references": unknown,
            "recommendation_count": len(report.recommendations),
            "interaction_count": len(report.interactions),
            "conflict_count": len(report.conflicts),
            "report_path": str(report_path),
        }

    benchmark = run_reasoning_benchmark(rule_registry=registry)
    if benchmark["failed"] > 0:
        failed_families.append("reasoning_benchmark")

    total_checks = len(SUPPORTED_MODEL_FAMILIES) + benchmark["total_cases"]
    failed_checks = len([family for family in SUPPORTED_MODEL_FAMILIES if not family_reports[family]["passed"]]) + benchmark["failed"]
    pass_rate = (total_checks - failed_checks) / total_checks if total_checks else 0.0
    return {
        "passed": failed_checks == 0,
        "pass_rate": pass_rate,
        "families": family_reports,
        "reasoning_benchmark": benchmark,
        "failed_families": failed_families,
        "unknown_rule_reference_count": unknown_rule_reference_count + benchmark["unknown_rule_reference_count"],
        "duplicate_recommendation_count": duplicate_recommendation_count + benchmark["duplicate_recommendation_count"],
        "missing_limitation_count": missing_limitation_count + benchmark["missing_limitation_count"],
    }


def _demo_section(output_root: Path) -> dict[str, Any]:
    from intentforge.demo_runner import run_demo

    result = run_demo(output_root)
    failed_steps = [
        step
        for step in result["steps"]
        if not step["ok"] and not step.get("intentional_rejection", False)
    ]
    return {
        "passed": result["benchmark"]["failed"] == 0 and not failed_steps,
        "run_id": result["run_id"],
        "benchmark": result["benchmark"],
        "failed_step_count": len(failed_steps),
        "demo_report_path": result["demo_report_path"],
        "demo_summary_path": result["demo_summary_path"],
        "persistent_output_dir": result["output_dir"],
    }


def _section_error_count(section: dict[str, Any]) -> int:
    return 1 if section.get("error_type") else 0


def _failure_type_count(section: dict[str, Any], failure_type: str) -> int:
    failure_types = section.get("failure_types")
    if not isinstance(failure_types, dict):
        return 0
    return int(failure_types.get(failure_type, 0) or 0)


def _build_metrics(sections: dict[str, dict[str, Any]]) -> dict[str, float | int]:
    benchmark = sections.get("benchmark", {})
    sweep = sections.get("sweep", {})
    edit = sections.get("edit_preservation", {})
    adversarial = sections.get("adversarial_rejection", {})
    volume = sections.get("volume_delta", {})
    shape = sections.get("shape_inspection", {})
    feature_recognition = sections.get("feature_recognition", {})
    reasoning = sections.get("engineering_reasoning", {})
    demo = sections.get("demo", {})

    unexpected_failure_count = int(benchmark.get("failed_cases", 0) or 0)
    unexpected_failure_count += int(sweep.get("failed_cases", 0) or 0)
    unexpected_failure_count += int(edit.get("failed_steps", 0) or 0)
    unexpected_failure_count += int(adversarial.get("failed_cases", 0) or 0)
    unexpected_failure_count += len(volume.get("failed_families", []) or [])
    unexpected_failure_count += len(shape.get("failed_families", []) or [])
    unexpected_failure_count += len(reasoning.get("failed_families", []) or [])
    unexpected_failure_count += int(demo.get("failed_step_count", 0) or 0)
    unexpected_failure_count += sum(_section_error_count(section) for section in sections.values())

    unsafe_acceptance_count = _failure_type_count(adversarial, "unexpected_acceptance")
    unsafe_acceptance_count += _failure_type_count(edit, "unexpected_acceptance")

    unexpected_exception_count = sum(
        _failure_type_count(section, "unexpected_exception") for section in sections.values()
    )
    unexpected_exception_count += sum(_section_error_count(section) for section in sections.values())

    return {
        "benchmark_pass_rate": float(benchmark.get("pass_rate", 0.0) or 0.0),
        "sweep_pass_rate": float(sweep.get("pass_rate", 0.0) or 0.0),
        "edit_preservation_rate": float(edit.get("edit_preservation_rate", 0.0) or 0.0),
        "adversarial_rejection_success_rate": float(adversarial.get("rejection_success_rate", 0.0) or 0.0),
        "feature_recognition_pass_rate": float(feature_recognition.get("pass_rate", 0.0) or 0.0),
        "feature_recognition_warning_count": int(feature_recognition.get("warning_count", 0) or 0),
        "reasoning_generation_pass_rate": float(reasoning.get("pass_rate", 0.0) or 0.0),
        "unknown_rule_reference_count": int(reasoning.get("unknown_rule_reference_count", 0) or 0),
        "duplicate_recommendation_count": int(reasoning.get("duplicate_recommendation_count", 0) or 0),
        "missing_limitation_count": int(reasoning.get("missing_limitation_count", 0) or 0),
        "unexpected_failure_count": unexpected_failure_count,
        "unsafe_acceptance_count": unsafe_acceptance_count,
        "unexpected_exception_count": unexpected_exception_count,
    }


def compute_quality_gates(report: dict[str, Any]) -> dict[str, Any]:
    """Compute quality gate results for a technical harness report."""

    metrics = report.get("metrics", {})
    gates = dict(report.get("quality_gates") or QUALITY_GATES)
    failed_gates: list[dict[str, Any]] = []

    gate_specs = (
        ("benchmark_pass_rate_min", "benchmark_pass_rate", ">="),
        ("sweep_pass_rate_min", "sweep_pass_rate", ">="),
        ("edit_preservation_rate_min", "edit_preservation_rate", ">="),
        ("adversarial_rejection_success_rate_min", "adversarial_rejection_success_rate", ">="),
        ("reasoning_generation_pass_rate_min", "reasoning_generation_pass_rate", ">="),
        ("unexpected_failure_count_max", "unexpected_failure_count", "<="),
        ("unsafe_acceptance_count_max", "unsafe_acceptance_count", "<="),
        ("unexpected_exception_count_max", "unexpected_exception_count", "<="),
        ("unknown_rule_reference_count_max", "unknown_rule_reference_count", "<="),
        ("duplicate_recommendation_count_max", "duplicate_recommendation_count", "<="),
        ("missing_limitation_count_max", "missing_limitation_count", "<="),
    )
    for gate_name, metric_name, operator in gate_specs:
        expected = gates[gate_name]
        actual = metrics.get(metric_name, 0)
        failed = actual < expected if operator == ">=" else actual > expected
        if failed:
            failed_gates.append(
                {
                    "gate": gate_name,
                    "metric": metric_name,
                    "expected": expected,
                    "actual": actual,
                    "operator": operator,
                }
            )

    return {
        "quality_gates": gates,
        "failed_gates": failed_gates,
        "quality_gates_passed": not failed_gates,
    }


def _build_summary(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        f"Technical harness run: {report['run_id']}",
        f"Overall passed: {str(report['overall_passed']).lower()}",
        f"Quality gates passed: {str(report['quality_gates_passed']).lower()}",
        "Metrics:",
        f"  - benchmark_pass_rate: {metrics['benchmark_pass_rate']:.4f}",
        f"  - sweep_pass_rate: {metrics['sweep_pass_rate']:.4f}",
        f"  - edit_preservation_rate: {metrics['edit_preservation_rate']:.4f}",
        f"  - adversarial_rejection_success_rate: {metrics['adversarial_rejection_success_rate']:.4f}",
        f"  - feature_recognition_pass_rate: {float(metrics.get('feature_recognition_pass_rate', 0.0)):.4f}",
        f"  - feature_recognition_warning_count: {int(metrics.get('feature_recognition_warning_count', 0))}",
        f"  - reasoning_generation_pass_rate: {float(metrics.get('reasoning_generation_pass_rate', 0.0)):.4f}",
        f"  - unknown_rule_reference_count: {int(metrics.get('unknown_rule_reference_count', 0))}",
        f"  - duplicate_recommendation_count: {int(metrics.get('duplicate_recommendation_count', 0))}",
        f"  - missing_limitation_count: {int(metrics.get('missing_limitation_count', 0))}",
        f"  - unexpected_failure_count: {metrics['unexpected_failure_count']}",
        f"  - unsafe_acceptance_count: {metrics['unsafe_acceptance_count']}",
        f"  - unexpected_exception_count: {metrics['unexpected_exception_count']}",
        "Sections:",
    ]
    for name, section in report["sections"].items():
        if section.get("skipped"):
            status = "skipped"
        else:
            status = "passed" if section.get("passed") else "failed"
        lines.append(f"  - {name}: {status}")
    if report["failed_gates"]:
        lines.append("Failed gates:")
        for gate in report["failed_gates"]:
            lines.append(
                f"  - {gate['gate']}: actual {gate['actual']} must be {gate['operator']} {gate['expected']}"
            )
    else:
        lines.append("Failed gates: none")
    lines.append(f"Report path: {report['output_paths']['latest_report']}")
    lines.append(f"Summary path: {report['output_paths']['latest_summary']}")
    lines.append(f"Persistent output dir: {report['persistent_output_dir']}")
    return "\n".join(lines) + "\n"


def write_technical_harness_report(report: dict[str, Any], output_root: str | Path) -> dict[str, Any]:
    """Write latest and persistent technical harness reports."""

    output_path = Path(output_root)
    harness_root = output_path / "harness"
    run_id = report["run_id"]
    run_dir = harness_root / "technical_harness_runs" / run_id
    latest_report_path = harness_root / "technical_harness_report.json"
    latest_summary_path = harness_root / "technical_harness_summary.txt"
    persistent_report_path = run_dir / "technical_harness_report.json"
    persistent_summary_path = run_dir / "technical_harness_summary.txt"
    output_paths = {
        "latest_report": latest_report_path,
        "latest_summary": latest_summary_path,
        "persistent_report": persistent_report_path,
        "persistent_summary": persistent_summary_path,
    }
    report["output_paths"] = json_safe_paths(output_paths)
    report["persistent_output_dir"] = str(run_dir)
    report["summary"] = _build_summary(report)
    _write_json(report, latest_report_path)
    _write_text(report["summary"], latest_summary_path)
    _write_json(report, persistent_report_path)
    _write_text(report["summary"], persistent_summary_path)
    return report


def run_technical_harness(
    output_root: str | Path,
    quick: bool = False,
    include_demo: bool = False,
) -> dict[str, Any]:
    """Run the complete technical harness suite and apply quality gates."""

    _require_cadquery()
    output_path = Path(output_root)
    harness_root = output_path / "harness"
    run_context = create_run_context("technical harness", harness_root, "technical_harness_runs")
    section_output_root = run_context.run_dir / "section_outputs"

    sections = {
        "benchmark": _run_section("benchmark", lambda: _benchmark_section(section_output_root)),
        "sweep": _run_section("sweep", lambda: _sweep_section(section_output_root, quick=quick)),
        "edit_preservation": _run_section(
            "edit_preservation",
            lambda: _edit_preservation_section(section_output_root),
        ),
        "adversarial_rejection": _run_section(
            "adversarial_rejection",
            lambda: _adversarial_section(section_output_root),
        ),
        "volume_delta": _run_section("volume_delta", lambda: _volume_delta_section(run_context.run_dir)),
        "shape_inspection": _run_section(
            "shape_inspection",
            lambda: _shape_inspection_section(run_context.run_dir),
        ),
        "feature_recognition": _run_section(
            "feature_recognition",
            lambda: _feature_recognition_section(run_context.run_dir),
        ),
        "engineering_reasoning": _run_section(
            "engineering_reasoning",
            lambda: _reasoning_section(run_context.run_dir),
        ),
    }
    if include_demo:
        sections["demo"] = _run_section("demo", lambda: _demo_section(section_output_root))
    else:
        sections["demo"] = {
            "name": "demo",
            "passed": True,
            "skipped": True,
            "reason": "Run with --include-demo to include the demo workflow.",
        }

    report: dict[str, Any] = {
        "run_id": run_context.run_id,
        "created_at": run_context.created_at.isoformat(),
        "quick": quick,
        "include_demo": include_demo,
        "overall_passed": False,
        "quality_gates_passed": False,
        "sections": sections,
        "metrics": _build_metrics(sections),
        "quality_gates": dict(QUALITY_GATES),
        "failed_gates": [],
    }
    gate_result = compute_quality_gates(report)
    report.update(gate_result)
    report["overall_passed"] = report["quality_gates_passed"] and all(
        section.get("passed") or section.get("skipped") for section in sections.values()
    )
    return write_technical_harness_report(report, output_path)
