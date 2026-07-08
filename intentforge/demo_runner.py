"""Release demo workflow for IntentForge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark.run_benchmark import run_benchmark

from intentforge.output_manager import create_run_context
from intentforge.workflows import (
    default_output_root,
    edit_parse_apply_workflow,
    edit_parse_workflow,
    parse_build_workflow,
)

DEMO_PARSE_BUILD_PROMPTS = [
    "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
    "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with four corner screw holes and a center cutout.",
    "Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, and 6 mm thick.",
]
DEMO_EDIT_APPLY_PROMPTS = [
    ("bracket", "Make it 150 mm wide but keep the same thickness."),
    ("bracket", "Change it to four mounting holes."),
    ("l_bracket", "Make the base leg 120 mm long."),
]
DEMO_REJECTED_EDIT = "Make it better."


def _write_json(data: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _step_record(command: str, result: dict[str, Any], intentional_rejection: bool = False) -> dict[str, Any]:
    return {
        "command": command,
        "ok": bool(result.get("ok")),
        "accepted": result.get("accepted"),
        "validation_valid": result.get("validation_valid"),
        "cad_exported": result.get("cad_exported", "step" in result.get("latest_outputs", {})),
        "intentional_rejection": intentional_rejection,
        "message": result.get("message"),
        "run_id": result.get("run_id"),
        "latest_outputs": result.get("latest_outputs", {}),
        "persistent_outputs": result.get("persistent_outputs", {}),
        "persistent_output_dir": result.get("persistent_output_dir"),
    }


def _build_summary(report: dict[str, Any]) -> str:
    lines = [
        f"Demo run ID: {report['run_id']}",
        f"Output directory: {report['output_dir']}",
        "Commands run:",
    ]
    for step in report["steps"]:
        status = "succeeded" if step["ok"] else "rejected" if step["intentional_rejection"] else "failed"
        lines.append(f"  - {step['command']}: {status}")
        if step.get("validation_valid") is not None:
            lines.append(f"    validation_valid: {str(step['validation_valid']).lower()}")
        if step.get("cad_exported") is not None:
            lines.append(f"    cad_exported: {str(step['cad_exported']).lower()}")
        if step.get("persistent_output_dir"):
            lines.append(f"    output_dir: {step['persistent_output_dir']}")
    benchmark = report["benchmark"]
    lines.extend(
        [
            "Benchmark:",
            f"  total_cases: {benchmark['total_cases']}",
            f"  passed: {benchmark['passed']}",
            f"  failed: {benchmark['failed']}",
            f"  pass_rate: {benchmark['pass_rate']:.4f}",
            f"  report_path: {benchmark['report_path']}",
            f"Demo report: {report['demo_report_path']}",
            f"Demo summary: {report['demo_summary_path']}",
        ]
    )
    return "\n".join(lines) + "\n"


def run_demo(output_root: str | Path | None = None) -> dict[str, Any]:
    """Run the release demo and write demo artifacts."""

    root = Path(output_root) if output_root is not None else default_output_root()
    run_context = create_run_context("intentforge demo", root, "demo_runs")
    demo_dir = run_context.run_dir
    steps: list[dict[str, Any]] = []

    for prompt in DEMO_PARSE_BUILD_PROMPTS:
        result = parse_build_workflow(prompt, demo_dir)
        steps.append(_step_record(f'parse-build "{prompt}"', result))

    for target, edit_text in DEMO_EDIT_APPLY_PROMPTS:
        result = edit_parse_apply_workflow(target, edit_text, demo_dir)
        steps.append(_step_record(f'edit-parse-apply {target} "{edit_text}"', result))

    rejected_result = edit_parse_workflow(DEMO_REJECTED_EDIT, demo_dir, write_outputs=True)
    steps.append(_step_record(f'edit-parse "{DEMO_REJECTED_EDIT}"', rejected_result, intentional_rejection=True))

    benchmark_result = run_benchmark(output_root=demo_dir)
    steps.append(
        {
            "command": "benchmark",
            "ok": benchmark_result["failed"] == 0,
            "intentional_rejection": False,
            "total_cases": benchmark_result["total_cases"],
            "passed": benchmark_result["passed"],
            "failed": benchmark_result["failed"],
            "pass_rate": benchmark_result["pass_rate"],
            "report_path": benchmark_result["report_path"],
            "persistent_report_path": benchmark_result["persistent_report_path"],
            "persistent_output_dir": benchmark_result["run_dir"],
        }
    )

    report_path = demo_dir / "demo_report.json"
    summary_path = demo_dir / "demo_summary.txt"
    report = {
        "run_id": run_context.run_id,
        "created_at": run_context.created_at.isoformat(),
        "output_dir": str(demo_dir),
        "steps": steps,
        "benchmark": {
            "total_cases": benchmark_result["total_cases"],
            "passed": benchmark_result["passed"],
            "failed": benchmark_result["failed"],
            "pass_rate": benchmark_result["pass_rate"],
            "report_path": benchmark_result["report_path"],
            "summary_path": benchmark_result["summary_path"],
            "persistent_report_path": benchmark_result["persistent_report_path"],
            "persistent_summary_path": benchmark_result["persistent_summary_path"],
            "run_dir": benchmark_result["run_dir"],
        },
        "demo_report_path": str(report_path),
        "demo_summary_path": str(summary_path),
    }
    summary = _build_summary(report)
    report["summary"] = summary
    _write_json(report, report_path)
    _write_text(summary, summary_path)
    return report


def main() -> int:
    """Run the demo from `python demo/run_demo.py`."""

    report = run_demo()
    print(report["summary"], end="")
    return 0 if report["benchmark"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
