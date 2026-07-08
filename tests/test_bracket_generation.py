import json
from pathlib import Path

import pytest
import yaml

from intentforge.cli import main
from intentforge.features import feature_flags_for_parameter_table, make_mounting_hole_flag
from intentforge.generator.cadquery_generator import build_wall_bracket
from intentforge.parser import parse_prompt
from intentforge.schemas import FeaturePlan, IntentSpec, ParameterTable


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def _bbox(model):
    return model.val().BoundingBox()


def _volume(model) -> float:
    return model.val().Volume()


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def test_bracket_examples_load_into_schema_models() -> None:
    intent_data = json.loads((EXAMPLES_DIR / "bracket_intent.json").read_text())
    params_data = yaml.safe_load((EXAMPLES_DIR / "bracket_params.yaml").read_text())
    feature_data = json.loads((EXAMPLES_DIR / "bracket_feature_plan.json").read_text())

    intent = IntentSpec.model_validate(intent_data)
    parameters = ParameterTable.model_validate(params_data)
    feature_plan = FeaturePlan.model_validate(feature_data)

    assert intent.family == "wall_mounted_bracket"
    assert parameters.get("back_plate_width_mm").value == 120.0
    assert parameters.get("mounting_hole_spacing_mm").value == 44.0
    assert parameters.get("center_cutout_width_mm").value == 42.0
    assert all(step.reason for step in feature_plan.steps)


def test_default_bracket_builds_without_crashing() -> None:
    _require_cadquery()

    model = build_wall_bracket(_load_parameter_table())
    bbox = _bbox(model)

    assert bbox.xlen == pytest.approx(120.0)
    assert bbox.ylen == pytest.approx(80.0)
    assert bbox.zlen == pytest.approx(6.0)


def test_cli_build_example_creates_real_step_and_stl_files() -> None:
    _require_cadquery()

    result = main(["build-example", "bracket"])

    step_path = PROJECT_ROOT / "output" / "bracket.step"
    stl_path = PROJECT_ROOT / "output" / "bracket.stl"
    assert result == 0
    assert step_path.exists()
    assert step_path.stat().st_size > 0
    assert stl_path.exists()
    assert stl_path.stat().st_size > 0


def test_changing_width_changes_bounding_box_width() -> None:
    _require_cadquery()

    narrow_model = build_wall_bracket(_table_with_parameter_value("back_plate_width_mm", 90.0))
    wide_model = build_wall_bracket(_table_with_parameter_value("back_plate_width_mm", 140.0))

    assert _bbox(narrow_model).xlen == pytest.approx(90.0)
    assert _bbox(wide_model).xlen == pytest.approx(140.0)


def test_changing_thickness_changes_bounding_box_thickness() -> None:
    _require_cadquery()

    thin_model = build_wall_bracket(_table_with_parameter_value("back_plate_thickness_mm", 4.0))
    thick_model = build_wall_bracket(_table_with_parameter_value("back_plate_thickness_mm", 12.0))

    assert _bbox(thin_model).zlen == pytest.approx(4.0)
    assert _bbox(thick_model).zlen == pytest.approx(12.0)


def test_changing_hole_spacing_does_not_crash() -> None:
    _require_cadquery()

    model = build_wall_bracket(_table_with_parameter_value("mounting_hole_spacing_mm", 52.0))

    assert _bbox(model).ylen == pytest.approx(80.0)


def test_invalid_negative_width_is_rejected() -> None:
    bad_table = _table_with_parameter_value("back_plate_width_mm", -10.0)

    with pytest.raises(ValueError, match="back_plate_width_mm"):
        build_wall_bracket(bad_table)


def test_invalid_hole_diameter_is_rejected() -> None:
    bad_table = _table_with_parameter_value("mounting_hole_diameter_mm", 0.0)

    with pytest.raises(ValueError, match="mounting_hole_diameter_mm"):
        build_wall_bracket(bad_table)


def test_cutout_larger_than_plate_is_rejected() -> None:
    bad_table = _table_with_parameter_value("center_cutout_width_mm", 130.0)

    with pytest.raises(ValueError, match="center_cutout_width_mm"):
        build_wall_bracket(bad_table)


def test_model_builds_without_center_cutout_when_cutout_omitted() -> None:
    _require_cadquery()

    no_cutout = parse_prompt("Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.")
    with_cutout = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes and a center cutout."
    )

    no_cutout_model = build_wall_bracket(no_cutout.parameter_table)
    with_cutout_model = build_wall_bracket(with_cutout.parameter_table)

    assert "center_cutout_width_mm" not in no_cutout.parameter_table.by_name()
    assert _volume(no_cutout_model) > _volume(with_cutout_model)


def test_model_builds_with_center_cutout_when_requested() -> None:
    _require_cadquery()

    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes and a center cutout."
    )
    model = build_wall_bracket(parsed.parameter_table)

    assert "center_cutout_width_mm" in parsed.parameter_table.by_name()
    assert _bbox(model).xlen == pytest.approx(120.0)


def test_model_builds_without_mounting_holes_when_holes_omitted() -> None:
    _require_cadquery()

    no_holes = parse_prompt("Make a plain mounting plate 100 mm wide, 50 mm tall, and 6 mm thick.")
    with_holes = parse_prompt(
        "Make a plain mounting plate 100 mm wide, 50 mm tall, 6 mm thick, with two screw holes."
    )

    no_holes_model = build_wall_bracket(no_holes.parameter_table)
    with_holes_model = build_wall_bracket(with_holes.parameter_table)

    assert "mounting_hole_diameter_mm" not in no_holes.parameter_table.by_name()
    assert _volume(no_holes_model) > _volume(with_holes_model)


def test_model_builds_with_mounting_holes_when_requested() -> None:
    _require_cadquery()

    parsed = parse_prompt("Make a plain mounting plate 100 mm wide, 50 mm tall, 6 mm thick, with two screw holes.")
    model = build_wall_bracket(parsed.parameter_table)

    assert "mounting_hole_diameter_mm" in parsed.parameter_table.by_name()
    assert _bbox(model).xlen == pytest.approx(100.0)


def test_two_hole_model_builds_with_symmetric_horizontal_pattern() -> None:
    _require_cadquery()

    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.")
    model = build_wall_bracket(parsed.parameter_table)
    flags = parsed.parameter_table.metadata["feature_flags"]["mounting_holes"]

    assert flags["hole_count"] == 2
    assert flags["pattern"] == "symmetric_2_horizontal"
    assert _bbox(model).xlen == pytest.approx(120.0)


def test_four_hole_model_builds_with_rectangular_pattern() -> None:
    _require_cadquery()

    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with four corner screw holes."
    )
    model = build_wall_bracket(parsed.parameter_table)
    flags = parsed.parameter_table.metadata["feature_flags"]["mounting_holes"]

    assert flags["hole_count"] == 4
    assert flags["pattern"] == "rectangular_4"
    assert parsed.parameter_table.get("mounting_hole_spacing_x_mm").value == 80.0
    assert parsed.parameter_table.get("mounting_hole_spacing_y_mm").value == 30.0
    assert _bbox(model).ylen == pytest.approx(60.0)


def test_unsupported_hole_count_is_rejected() -> None:
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
    bad_table = table.model_copy(update={"parameters": parameters, "metadata": {**table.metadata, "feature_flags": flags}})

    with pytest.raises(ValueError, match="mounting_hole_count"):
        build_wall_bracket(bad_table)


def test_four_hole_spacing_changes_do_not_crash() -> None:
    _require_cadquery()

    parsed = parse_prompt(
        "Make a wall-mounted bracket 140 mm wide, 90 mm tall, 8 mm thick, with four corner screw holes."
    )
    table = parsed.parameter_table
    parameters = [
        parameter.model_copy(update={"value": 90.0})
        if parameter.name == "mounting_hole_spacing_x_mm"
        else parameter.model_copy(update={"value": 40.0})
        if parameter.name == "mounting_hole_spacing_y_mm"
        else parameter
        for parameter in table.parameters
    ]
    model = build_wall_bracket(table.model_copy(update={"parameters": parameters}))

    assert _bbox(model).xlen == pytest.approx(140.0)
    assert _bbox(model).ylen == pytest.approx(90.0)
