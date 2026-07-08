from pathlib import Path

import pytest
import yaml

from intentforge.features import feature_flags_for_parameter_table, make_feature_flag, make_mounting_hole_flag
from intentforge.generator.cadquery_generator import build_wall_bracket, export_model
from intentforge.parser import parse_prompt
from intentforge.schemas import Parameter, ParameterTable
from intentforge.validator.geometry_validator import validate_wall_bracket


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def _load_parameter_table() -> ParameterTable:
    params_data = yaml.safe_load((EXAMPLES_DIR / "bracket_params.yaml").read_text())
    return ParameterTable.model_validate(params_data)


def _table_with_parameter_value(name: str, value: float) -> ParameterTable:
    table = _load_parameter_table()
    parameters = [
        parameter.model_copy(update={"value": value}) if parameter.name == name else parameter
        for parameter in table.parameters
    ]
    return table.model_copy(update={"parameters": parameters})


def _parsed_table_with_parameter_value(prompt: str, name: str, value: float) -> ParameterTable:
    table = parse_prompt(prompt).parameter_table
    parameters = [
        parameter.model_copy(update={"value": value}) if parameter.name == name else parameter
        for parameter in table.parameters
    ]
    return table.model_copy(update={"parameters": parameters})


def _table_with_feature_active(table: ParameterTable, feature: str) -> ParameterTable:
    flags = feature_flags_for_parameter_table(table)
    flags[feature] = make_feature_flag("requested_by_user", f"{feature} activated for validation test.")
    metadata = {**table.metadata, "feature_flags": flags}
    return table.model_copy(update={"metadata": metadata})


def _check(report, check_id: str):
    checks = {check.id: check for check in report.checks}
    return checks[check_id]


def test_default_bracket_passes_geometry_validation() -> None:
    _require_cadquery()

    table = _load_parameter_table()
    model = build_wall_bracket(table)
    report = validate_wall_bracket(model, table)

    assert report.valid is True
    assert report.failed_checks == []


def test_changed_width_validates_when_parameter_table_matches_model() -> None:
    _require_cadquery()

    table = _table_with_parameter_value("back_plate_width_mm", 140.0)
    model = build_wall_bracket(table)
    report = validate_wall_bracket(model, table)

    assert report.valid is True
    assert _check(report, "bounding_box_width_check").actual == pytest.approx(140.0)


def test_invalid_negative_width_fails_validation_without_building() -> None:
    table = _table_with_parameter_value("back_plate_width_mm", -10.0)

    report = validate_wall_bracket(None, table)

    assert report.valid is False
    assert _check(report, "parameter_range_check").passed is False


def test_invalid_hole_diameter_fails_validation() -> None:
    table = _table_with_parameter_value("mounting_hole_diameter_mm", 75.0)

    report = validate_wall_bracket(None, table)

    assert report.valid is False
    assert _check(report, "hole_diameter_range_check").passed is False


def test_invalid_hole_spacing_fails_validation() -> None:
    table = _table_with_parameter_value("mounting_hole_spacing_mm", 120.0)

    report = validate_wall_bracket(None, table)

    assert report.valid is False
    assert _check(report, "hole_spacing_range_check").passed is False


def test_valid_two_hole_pattern_passes_validation() -> None:
    _require_cadquery()

    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.")
    model = build_wall_bracket(parsed.parameter_table)
    report = validate_wall_bracket(model, parsed.parameter_table)

    assert report.valid is True
    assert _check(report, "hole_pattern_check").passed is True
    assert _check(report, "hole_spacing_range_check").passed is True


def test_valid_four_hole_pattern_passes_validation() -> None:
    _require_cadquery()

    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with four corner screw holes."
    )
    model = build_wall_bracket(parsed.parameter_table)
    report = validate_wall_bracket(model, parsed.parameter_table)

    assert report.valid is True
    assert _check(report, "hole_pattern_check").passed is True
    assert _check(report, "hole_spacing_range_check").metadata["hole_count"] == 4


def test_four_hole_x_spacing_too_large_fails_validation() -> None:
    table = _parsed_table_with_parameter_value(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with four corner screw holes.",
        "mounting_hole_spacing_x_mm",
        116.0,
    )

    report = validate_wall_bracket(None, table)

    assert report.valid is False
    assert _check(report, "hole_spacing_range_check").passed is False
    assert "x=" in _check(report, "hole_spacing_range_check").actual


def test_four_hole_y_spacing_too_large_fails_validation() -> None:
    table = _parsed_table_with_parameter_value(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with four corner screw holes.",
        "mounting_hole_spacing_y_mm",
        56.0,
    )

    report = validate_wall_bracket(None, table)

    assert report.valid is False
    assert _check(report, "hole_spacing_range_check").passed is False
    assert "y=" in _check(report, "hole_spacing_range_check").actual


def test_unsupported_hole_count_fails_validation() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.")
    table = parsed.parameter_table
    parameters = [
        parameter.model_copy(update={"value": 3})
        if parameter.name == "mounting_hole_count"
        else parameter
        for parameter in table.parameters
    ]
    flags = feature_flags_for_parameter_table(table)
    flags["mounting_holes"] = make_mounting_hole_flag("requested_by_user", "Unsupported test pattern.", 3)
    table = table.model_copy(update={"parameters": parameters, "metadata": {**table.metadata, "feature_flags": flags}})

    report = validate_wall_bracket(None, table)

    assert report.valid is False
    assert _check(report, "hole_pattern_check").passed is False


def test_oversized_cutout_fails_validation() -> None:
    table = _table_with_parameter_value("center_cutout_width_mm", 118.0)

    report = validate_wall_bracket(None, table)

    assert report.valid is False
    assert _check(report, "cutout_inside_plate_check").passed is False


def test_corner_radius_too_large_fails_validation() -> None:
    table = _table_with_parameter_value("corner_radius_mm", 45.0)

    report = validate_wall_bracket(None, table)

    assert report.valid is False
    assert _check(report, "corner_radius_limit_check").passed is False


def test_edge_fillet_radius_too_large_fails_validation() -> None:
    table = _table_with_feature_active(_table_with_parameter_value("fillet_radius_mm", 4.0), "edge_fillets")

    report = validate_wall_bracket(None, table)

    assert report.valid is False
    assert _check(report, "edge_fillet_limit_check").passed is False


def test_no_cutout_prompt_validates_without_cutout_check_failure() -> None:
    _require_cadquery()

    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.")
    model = build_wall_bracket(parsed.parameter_table)
    report = validate_wall_bracket(model, parsed.parameter_table)

    assert report.valid is True
    assert "cutout_inside_plate_check" not in {check.id for check in report.checks}


def test_requested_cutout_validates_cutout_dimensions() -> None:
    _require_cadquery()

    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes and a center cutout."
    )
    model = build_wall_bracket(parsed.parameter_table)
    report = validate_wall_bracket(model, parsed.parameter_table)

    assert report.valid is True
    assert _check(report, "cutout_inside_plate_check").passed is True


def test_oversized_cutout_is_ignored_when_cutout_is_omitted() -> None:
    _require_cadquery()

    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.")
    table = parsed.parameter_table.model_copy(
        update={
            "parameters": [
                *parsed.parameter_table.parameters,
                Parameter(
                    name="center_cutout_width_mm",
                    value=118.0,
                    unit="mm",
                    description="Inactive cutout width.",
                    source="user",
                    reason="Present only to verify omitted cutout validation behavior.",
                    min_value=1.0,
                ),
                Parameter(
                    name="center_cutout_height_mm",
                    value=58.0,
                    unit="mm",
                    description="Inactive cutout height.",
                    source="user",
                    reason="Present only to verify omitted cutout validation behavior.",
                    min_value=1.0,
                ),
            ]
        }
    )
    model = build_wall_bracket(table)
    report = validate_wall_bracket(model, table)

    assert report.valid is True
    assert "cutout_inside_plate_check" not in {check.id for check in report.checks}


def test_missing_export_files_fail_export_files_exist_check(tmp_path) -> None:
    table = _load_parameter_table()
    output_paths = {
        "step": tmp_path / "missing.step",
        "stl": tmp_path / "missing.stl",
    }

    report = validate_wall_bracket(None, table, output_paths=output_paths)

    assert report.valid is False
    assert _check(report, "export_files_exist_check").passed is False


def test_real_exported_step_and_stl_files_pass_export_check(tmp_path) -> None:
    _require_cadquery()

    table = _load_parameter_table()
    model = build_wall_bracket(table)
    step_path = tmp_path / "bracket.step"
    stl_path = tmp_path / "bracket.stl"
    export_model(model, step_path, stl_path)

    report = validate_wall_bracket(
        model,
        table,
        output_paths={"step": step_path, "stl": stl_path},
    )

    assert report.valid is True
    assert _check(report, "export_files_exist_check").passed is True
