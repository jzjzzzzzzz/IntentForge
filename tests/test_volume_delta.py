import json
from pathlib import Path

import pytest
import yaml

from harness.topology.volume_delta import (
    build_volume_delta_report,
    compare_volume_delta,
    estimate_wall_bracket_hole_volume,
    l_bracket_volume_delta_checks,
    wall_bracket_volume_delta_checks,
)
from intentforge.cli import main
from intentforge.generator.cadquery_generator import build_l_bracket, build_wall_bracket
from intentforge.parser import parse_prompt
from intentforge.schemas import ParameterTable
from intentforge.validator.geometry_validator import validate_l_bracket, validate_wall_bracket


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def _example_parameters(filename: str) -> ParameterTable:
    return ParameterTable.model_validate(
        yaml.safe_load((PROJECT_ROOT / "examples" / filename).read_text(encoding="utf-8"))
    )


def _check_by_id(records: list[dict], check_id: str) -> dict:
    for record in records:
        if record["id"] == check_id:
            return record
    raise AssertionError(f"missing volume delta record: {check_id}")


def test_estimated_wall_hole_volume_is_positive() -> None:
    table = _example_parameters("bracket_params.yaml")

    assert estimate_wall_bracket_hole_volume(table) > 0


def test_invalid_volume_comparison_warns_without_crashing() -> None:
    result = compare_volume_delta(10.0, None)

    assert result["warning"] is True
    assert result["passed"] is False


def test_wall_bracket_two_holes_have_negative_volume_delta() -> None:
    _require_cadquery()

    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes."
    )
    model = build_wall_bracket(parsed.parameter_table)
    checks, records = wall_bracket_volume_delta_checks(parsed.parameter_table, model)
    record = _check_by_id(records, "mounting_hole_volume_delta_check")

    assert record["actual_delta_mm3"] < 0
    assert record["expected_delta_mm3"] < 0
    assert record["status"] == "pass"
    assert all(check.id != "center_cutout_volume_delta_check" for check in checks)


def test_wall_bracket_cutout_has_negative_volume_delta() -> None:
    _require_cadquery()

    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes and a center cutout."
    )
    model = build_wall_bracket(parsed.parameter_table)
    _, records = wall_bracket_volume_delta_checks(parsed.parameter_table, model)
    record = _check_by_id(records, "center_cutout_volume_delta_check")

    assert record["actual_delta_mm3"] < 0
    assert record["expected_delta_mm3"] < 0
    assert record["status"] == "pass"


def test_l_bracket_gusset_increases_volume() -> None:
    _require_cadquery()

    parsed = parse_prompt(
        "Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, 6 mm thick, with a triangular gusset."
    )
    model = build_l_bracket(parsed.parameter_table)
    _, records = l_bracket_volume_delta_checks(parsed.parameter_table, model)
    record = _check_by_id(records, "gusset_volume_delta_check")

    assert record["actual_delta_mm3"] > 0
    assert record["expected_delta_mm3"] > 0
    assert record["status"] == "pass"


def test_l_bracket_base_and_vertical_holes_reduce_volume() -> None:
    _require_cadquery()

    table = _example_parameters("l_bracket_params.yaml")
    model = build_l_bracket(table)
    _, records = l_bracket_volume_delta_checks(table, model)
    base_record = _check_by_id(records, "base_hole_volume_delta_check")
    vertical_record = _check_by_id(records, "vertical_hole_volume_delta_check")

    assert base_record["actual_delta_mm3"] < 0
    assert base_record["expected_delta_mm3"] < 0
    assert vertical_record["actual_delta_mm3"] < 0
    assert vertical_record["expected_delta_mm3"] < 0


def test_l_bracket_without_gusset_skips_gusset_delta_check() -> None:
    _require_cadquery()

    table = _example_parameters("l_bracket_params.yaml")
    model = build_l_bracket(table)
    checks, records = l_bracket_volume_delta_checks(table, model)

    assert all(check.id != "gusset_volume_delta_check" for check in checks)
    assert all(record["id"] != "gusset_volume_delta_check" for record in records)


def test_validation_report_includes_volume_delta_checks() -> None:
    _require_cadquery()

    table = _example_parameters("bracket_params.yaml")
    model = build_wall_bracket(table)
    report = validate_wall_bracket(model, table)
    check_ids = {check.id for check in report.checks}

    assert "mounting_hole_volume_delta_check" in check_ids
    assert "center_cutout_volume_delta_check" in check_ids
    assert report.metadata["volume_delta_checks"]


def test_l_bracket_validation_report_includes_hole_delta_checks() -> None:
    _require_cadquery()

    table = _example_parameters("l_bracket_params.yaml")
    model = build_l_bracket(table)
    report = validate_l_bracket(model, table)
    check_ids = {check.id for check in report.checks}

    assert "base_hole_volume_delta_check" in check_ids
    assert "vertical_hole_volume_delta_check" in check_ids


def test_cli_volume_delta_wall_bracket_creates_persistent_report(capsys: pytest.CaptureFixture[str]) -> None:
    _require_cadquery()

    result = main(["volume-delta", "wall_mounted_bracket"])

    output = capsys.readouterr().out
    latest_path = PROJECT_ROOT / "output" / "harness" / "volume_delta_report.json"
    assert result == 0
    assert "Volume delta run:" in output
    assert latest_path.exists()
    report = json.loads(latest_path.read_text(encoding="utf-8"))
    persistent_path = Path(report["output_paths"]["persistent_report"])
    assert persistent_path.exists()
    assert persistent_path.parent.parent.name == "volume_delta_runs"


def test_cli_volume_delta_l_bracket_runs(capsys: pytest.CaptureFixture[str]) -> None:
    _require_cadquery()

    result = main(["volume-delta", "l_bracket"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Object type: l_bracket" in output


def test_build_volume_delta_report_has_no_gusset_check_for_no_gusset_l_bracket() -> None:
    _require_cadquery()

    table = _example_parameters("l_bracket_params.yaml")
    model = build_l_bracket(table)
    report = build_volume_delta_report(table, model)

    assert all(check["id"] != "gusset_volume_delta_check" for check in report["checks"])
