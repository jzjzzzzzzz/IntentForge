import json
from pathlib import Path

import pytest
import yaml

from harness.topology import (
    recognize_features,
    recognize_l_bracket_features,
    recognize_wall_bracket_features,
    write_feature_recognition_report,
)
from intentforge.cli import main
from intentforge.generator.cadquery_generator import build_l_bracket, build_wall_bracket
from intentforge.parser import parse_prompt
from intentforge.schemas import ParameterTable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def _example_parameters(filename: str) -> ParameterTable:
    return ParameterTable.model_validate(
        yaml.safe_load((PROJECT_ROOT / "examples" / filename).read_text(encoding="utf-8"))
    )


def test_feature_recognizer_imports() -> None:
    assert callable(recognize_features)
    assert callable(recognize_wall_bracket_features)
    assert callable(recognize_l_bracket_features)


def test_wall_bracket_two_holes_are_recognized_or_warn() -> None:
    _require_cadquery()

    table = _example_parameters("bracket_params.yaml")
    model = build_wall_bracket(table)
    report = recognize_wall_bracket_features(model, table)
    holes = report["recognized_features"]["through_holes"]

    assert holes["expected_count"] == 2
    assert holes["passed"] or holes["warnings"]
    if holes["passed"]:
        assert holes["recognized_count"] == 2


def test_wall_bracket_center_cutout_is_recognized_or_warns() -> None:
    _require_cadquery()

    table = _example_parameters("bracket_params.yaml")
    model = build_wall_bracket(table)
    report = recognize_wall_bracket_features(model, table)
    cutout = report["recognized_features"]["center_cutout"]

    assert cutout["expected"] is True
    assert cutout["passed"] or cutout["warnings"]


def test_l_bracket_connected_solid_is_recognized() -> None:
    _require_cadquery()

    table = _example_parameters("l_bracket_params.yaml")
    model = build_l_bracket(table)
    report = recognize_l_bracket_features(model, table)

    assert report["topology_checks"]["solid_count"] == 1
    assert report["topology_checks"]["connected_solid"] is True
    assert report["recognized_features"]["solid_connection"]["passed"] is True


def test_l_bracket_gusset_is_recognized_or_warns() -> None:
    _require_cadquery()

    parsed = parse_prompt(
        "Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, 6 mm thick, with a triangular gusset."
    )
    model = build_l_bracket(parsed.parameter_table)
    report = recognize_l_bracket_features(model, parsed.parameter_table)
    gusset = report["recognized_features"]["triangular_gusset"]

    assert gusset["expected"] is True
    assert gusset["passed"] or gusset["warnings"]


def test_feature_recognition_report_writing(tmp_path: Path) -> None:
    report = {
        "object_type": "wall_mounted_bracket",
        "recognized_features": {},
        "topology_checks": {},
        "passed": True,
        "warnings": [],
        "metadata": {},
    }

    path = write_feature_recognition_report(report, tmp_path / "feature_recognition_report.json")

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["object_type"] == "wall_mounted_bracket"


def test_cli_recognize_features_runs_when_cadquery_available(capsys: pytest.CaptureFixture[str]) -> None:
    _require_cadquery()

    result = main(["recognize-features", "wall_mounted_bracket"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Feature recognition run:" in output
    latest = PROJECT_ROOT / "output" / "harness" / "feature_recognition_report.json"
    assert latest.exists()
    report = json.loads(latest.read_text(encoding="utf-8"))
    assert report["object_type"] == "wall_mounted_bracket"
    assert "through_holes" in report["recognized_features"]
