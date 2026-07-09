import json
from pathlib import Path

import pytest
import yaml

from intentforge.cli import main
from intentforge.reports.design_review import (
    generate_design_review_report,
    write_design_review_report,
    write_design_review_summary,
)
from intentforge.schemas import ParameterTable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def _example_parameters(filename: str) -> ParameterTable:
    return ParameterTable.model_validate(
        yaml.safe_load((PROJECT_ROOT / "examples" / filename).read_text(encoding="utf-8"))
    )


def test_design_review_report_includes_requested_sections() -> None:
    table = _example_parameters("bracket_params.yaml")

    report = generate_design_review_report(
        intent_spec=None,
        parameter_table=table,
        validation_report=None,
        topology_report=None,
        volume_delta_report=None,
        feature_recognition_report=None,
    )

    assert report["object_type"] == "wall_mounted_bracket"
    assert "requested" in report
    assert "parameters" in report
    assert "features" in report
    assert "validation" in report
    assert "topology" in report
    assert "feature_recognition" in report
    assert "limitations" in report


def test_design_review_report_writing(tmp_path: Path) -> None:
    table = _example_parameters("bracket_params.yaml")
    report = generate_design_review_report(intent_spec=None, parameter_table=table)

    json_path = write_design_review_report(report, tmp_path / "design_review_report.json")
    markdown_path = write_design_review_summary(report, tmp_path / "design_review_summary.md")

    assert json_path.exists()
    assert markdown_path.exists()
    assert json.loads(json_path.read_text(encoding="utf-8"))["object_type"] == "wall_mounted_bracket"
    assert "# IntentForge Design Review" in markdown_path.read_text(encoding="utf-8")


def test_cli_design_review_runs_when_cadquery_available(capsys: pytest.CaptureFixture[str]) -> None:
    _require_cadquery()

    result = main(["design-review", "l_bracket"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Design review run:" in output
    latest_report = PROJECT_ROOT / "output" / "design_review_report.json"
    latest_summary = PROJECT_ROOT / "output" / "design_review_summary.md"
    assert latest_report.exists()
    assert latest_summary.exists()
    report = json.loads(latest_report.read_text(encoding="utf-8"))
    assert report["object_type"] == "l_bracket"
    assert "feature_recognition" in report
