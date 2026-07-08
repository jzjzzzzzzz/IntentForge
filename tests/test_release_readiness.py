import importlib
import json
from pathlib import Path

import pytest

from intentforge.cli import main
from intentforge.demo_runner import run_demo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOC_FILES = [
    "architecture.md",
    "design_intent.md",
    "workflow_examples.md",
    "validation.md",
    "benchmark.md",
    "mcp.md",
    "roadmap.md",
]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def test_docs_files_exist() -> None:
    for filename in DOC_FILES:
        path = PROJECT_ROOT / "docs" / filename
        assert path.exists(), filename
        assert path.read_text(encoding="utf-8").strip()


def test_readme_contains_major_sections() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "IntentForge",
        "Pipeline",
        "Why This Is Different",
        "Supported Scope",
        "Installation",
        "Usage",
        "Demo",
        "Benchmark",
        "MCP Usage",
        "Project Structure",
        "Roadmap",
        "wall_mounted_bracket",
        "deterministic regex",
    ]
    for text in required:
        assert text in readme


def test_release_status_files_exist() -> None:
    assert (PROJECT_ROOT / "PROJECT_STATUS.md").exists()
    assert (PROJECT_ROOT / "RELEASE_CHECKLIST.md").exists()


def test_demo_script_can_be_imported() -> None:
    module = importlib.import_module("demo.run_demo")

    assert hasattr(module, "run_demo")


def test_demo_report_is_generated(tmp_path: Path) -> None:
    _require_cadquery()

    result = run_demo(tmp_path / "output")
    report_path = Path(result["demo_report_path"])
    summary_path = Path(result["demo_summary_path"])

    assert report_path.exists()
    assert summary_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["benchmark"]["failed"] == 0
    assert any(step["intentional_rejection"] and not step["ok"] for step in report["steps"])
    assert any("step" in (step.get("persistent_outputs") or {}) for step in report["steps"])


def test_cli_demo_command_works(tmp_path: Path) -> None:
    _require_cadquery()

    result = main(["demo", "--output-root", str(tmp_path / "output")])

    assert result == 0
    demo_runs = tmp_path / "output" / "demo_runs"
    assert demo_runs.exists()
    reports = list(demo_runs.glob("*/demo_report.json"))
    assert reports

