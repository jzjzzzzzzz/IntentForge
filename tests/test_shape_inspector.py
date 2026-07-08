import json
from pathlib import Path

import pytest
import yaml

from harness.topology import inspect_shape
from intentforge.cli import main
from intentforge.generator.cadquery_generator import build_l_bracket, build_wall_bracket
from intentforge.schemas import ParameterTable
from intentforge.validator.geometry_validator import validate_wall_bracket


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def _example_parameters(filename: str) -> ParameterTable:
    return ParameterTable.model_validate(
        yaml.safe_load((PROJECT_ROOT / "examples" / filename).read_text(encoding="utf-8"))
    )


def test_shape_inspector_runs_for_wall_mounted_bracket() -> None:
    _require_cadquery()

    parameters = _example_parameters("bracket_params.yaml")
    model = build_wall_bracket(parameters)
    report = inspect_shape(model, family=parameters.family)

    assert report.family == "wall_mounted_bracket"
    assert report.bounding_box_dimensions_mm is not None
    assert report.bounding_box_dimensions_mm["x"] > 0
    assert report.volume_mm3 is not None
    assert report.volume_mm3 > 0
    assert report.face_count is not None
    assert report.edge_count is not None
    assert report.solid_count is not None


def test_shape_inspector_runs_for_l_bracket() -> None:
    _require_cadquery()

    parameters = _example_parameters("l_bracket_params.yaml")
    model = build_l_bracket(parameters)
    report = inspect_shape(model, family=parameters.family)

    assert report.family == "l_bracket"
    assert report.bounding_box_dimensions_mm is not None
    assert report.bounding_box_dimensions_mm["z"] > 0
    assert report.volume_mm3 is not None
    assert report.volume_mm3 > 0
    assert report.face_count is not None
    assert report.edge_count is not None
    assert report.solid_count is not None


def test_shape_inspector_missing_optional_topology_fields_warns() -> None:
    class FakeBoundingBox:
        xlen = 10
        ylen = 20
        zlen = 3

    class MinimalShape:
        def BoundingBox(self):
            return FakeBoundingBox()

        def Volume(self):
            return 600

    report = inspect_shape(MinimalShape(), family="test_shape")

    assert report.bounding_box_dimensions_mm == {"x": 10.0, "y": 20.0, "z": 3.0}
    assert report.volume_mm3 == 600.0
    assert report.surface_area_mm2 is None
    assert report.face_count is None
    assert report.edge_count is None
    assert report.warnings
    warning_metrics = {warning.metric for warning in report.warnings}
    assert "surface_area" in warning_metrics
    assert "face_count" in warning_metrics


def test_geometry_validation_includes_topology_metadata() -> None:
    _require_cadquery()

    parameters = _example_parameters("bracket_params.yaml")
    model = build_wall_bracket(parameters)
    report = validate_wall_bracket(model, parameters)

    topology = report.metadata.get("topology")
    assert topology is not None
    assert topology["bounding_box_dimensions_mm"]["x"] > 0
    assert topology["volume_mm3"] > 0


def test_cli_inspect_shape_writes_report(capsys: pytest.CaptureFixture[str]) -> None:
    _require_cadquery()

    result = main(["inspect-shape", "wall_mounted_bracket"])

    output = capsys.readouterr().out
    report_path = PROJECT_ROOT / "output" / "harness" / "topology_report.json"
    assert result == 0
    assert "Bounding box:" in output
    assert "Volume:" in output
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["family"] == "wall_mounted_bracket"
    assert report["bounding_box_dimensions_mm"]["x"] > 0
