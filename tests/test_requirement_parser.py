from datetime import datetime
import json
from pathlib import Path
import re

import pytest
import yaml

from intentforge.cli import main
from intentforge.features import feature_flags_for_parameter_table, is_feature_active
from intentforge.output_manager import create_parsed_run_context, make_run_id
from intentforge.parser import UnsupportedObjectError, parse_prompt
from intentforge.planner.feature_planner import plan_wall_bracket_features


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def _value(parsed, name: str):
    return parsed.parameter_table.get(name).value


def _step_ids(parsed) -> list[str]:
    return [step.id for step in parsed.feature_plan.steps]


def _is_active(parsed, feature: str) -> bool:
    return is_feature_active(feature_flags_for_parameter_table(parsed.parameter_table), feature)


def _run_dirs() -> set[Path]:
    runs_dir = PROJECT_ROOT / "output" / "parsed_runs"
    if not runs_dir.exists():
        return set()
    return {path for path in runs_dir.iterdir() if path.is_dir()}


def _new_run_dirs(before: set[Path]) -> list[Path]:
    return sorted(_run_dirs() - before, key=lambda path: path.name)


def test_generated_run_id_is_filesystem_safe_and_includes_prompt_slug() -> None:
    run_id = make_run_id(
        "Make a wall-mounted bracket 120 mm wide.",
        datetime(2026, 7, 8, 15, 30, 12),
    )

    assert run_id.startswith("20260708_153012_")
    assert "wall_mounted_bracket" in run_id
    assert "120mm" in run_id
    assert re.fullmatch(r"[a-z0-9_]+", run_id)


def test_duplicate_run_id_collisions_do_not_overwrite_previous_directories(tmp_path) -> None:
    prompt = "Make a wall-mounted bracket 120 mm wide."
    created_at = datetime(2026, 7, 8, 15, 30, 12)

    first = create_parsed_run_context(prompt, tmp_path, created_at)
    marker = first.run_dir / "marker.txt"
    marker.write_text("first run", encoding="utf-8")
    second = create_parsed_run_context(prompt, tmp_path, created_at)

    assert second.run_id == f"{first.run_id}_2"
    assert first.run_dir != second.run_dir
    assert marker.read_text(encoding="utf-8") == "first run"


def test_extracts_width_from_value_before_wide() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide with two screw holes and a center cutout.")

    assert _value(parsed, "back_plate_width_mm") == 120.0


def test_extracts_width_from_width_before_value() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket with width 120 mm and a center cutout.")

    assert _value(parsed, "back_plate_width_mm") == 120.0


def test_extracts_height_from_tall() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 60 mm tall with two screw holes and a center cutout.")

    assert _value(parsed, "back_plate_height_mm") == 60.0


def test_extracts_thickness_from_thick() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 8 mm thick with two screw holes and a center cutout.")

    assert _value(parsed, "back_plate_thickness_mm") == 8.0


def test_extracts_hole_diameter_from_holes() -> None:
    parsed = parse_prompt("Create a bracket with 150 mm width, 80 mm height, 10 mm thickness, and 6 mm holes.")

    assert _value(parsed, "mounting_hole_diameter_mm") == 6.0


def test_detects_two_screw_holes() -> None:
    parsed = parse_prompt("I need a mounting plate with two symmetric screw holes and a rectangular center cutout.")

    assert _value(parsed, "mounting_hole_count") == 2
    assert _value(parsed, "mounting_hole_spacing_mm") == 80.0
    assert parsed.parameter_table.metadata["feature_flags"]["mounting_holes"]["pattern"] == "symmetric_2_horizontal"


def test_prompt_with_four_holes_sets_rectangular_pattern() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with four screw holes.")

    flags = parsed.parameter_table.metadata["feature_flags"]["mounting_holes"]
    assert _value(parsed, "mounting_hole_count") == 4
    assert _value(parsed, "mounting_hole_spacing_x_mm") == 80.0
    assert _value(parsed, "mounting_hole_spacing_y_mm") == 30.0
    assert flags["pattern"] == "rectangular_4"
    assert "Hole spacing X defaulted to width - 40 mm." in parsed.intent.assumptions
    assert "Hole spacing Y defaulted to height - 30 mm." in parsed.intent.assumptions


def test_prompt_with_four_corner_holes_sets_rectangular_pattern() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with four corner holes.")

    assert _value(parsed, "mounting_hole_count") == 4
    assert parsed.parameter_table.metadata["feature_flags"]["mounting_holes"]["pattern"] == "rectangular_4"
    mounting_step = next(step for step in parsed.feature_plan.steps if step.id == "cut_mounting_holes")
    assert mounting_step.metadata["pattern"] == "rectangular_4"


def test_prompt_with_no_holes_omits_mounting_holes() -> None:
    parsed = parse_prompt("Make a plain mounting plate 100 mm wide, 50 mm tall, and 6 mm thick with no holes.")

    flags = parsed.parameter_table.metadata["feature_flags"]["mounting_holes"]
    assert flags["state"] == "omitted"
    assert flags["pattern"] == "none"
    assert "mounting_hole_count" not in parsed.parameter_table.by_name()
    assert "cut_mounting_holes" not in _step_ids(parsed)


def test_prompt_with_hole_spacing_by_extracts_x_y_spacing() -> None:
    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide, 80 mm tall, with four holes spaced 100 mm by 50 mm."
    )

    assert _value(parsed, "mounting_hole_count") == 4
    assert _value(parsed, "mounting_hole_spacing_x_mm") == 100.0
    assert _value(parsed, "mounting_hole_spacing_y_mm") == 50.0


def test_detects_two_six_mm_screw_holes() -> None:
    parsed = parse_prompt(
        "Make a wall-mounted bracket 150 mm wide, 80 mm tall, with two 6 mm screw holes and a center cutout."
    )

    assert _value(parsed, "mounting_hole_count") == 2
    assert _value(parsed, "mounting_hole_diameter_mm") == 6.0


def test_detects_rounded_corners() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket with rounded corners and two screw holes.")

    assert _value(parsed, "corner_radius_mm") == 4.0
    assert "Corner radius defaulted to 4 mm." in parsed.intent.assumptions
    assert _is_active(parsed, "rounded_corners") is True


def test_detects_center_cutout() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket with two screw holes and a rectangular center cutout.")

    assert _value(parsed, "center_cutout_width_mm") == 42.0
    assert _value(parsed, "center_cutout_height_mm") == 18.0
    assert "Cutout width defaulted to width * 0.35." in parsed.intent.assumptions
    assert _is_active(parsed, "center_cutout") is True


def test_missing_thickness_defaults_to_8_mm() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.")

    assert _value(parsed, "back_plate_thickness_mm") == 8.0
    assert "Thickness defaulted to 8 mm." in parsed.intent.assumptions


def test_missing_hole_diameter_defaults_to_5_mm() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket with two screw holes and a center cutout.")

    assert _value(parsed, "mounting_hole_diameter_mm") == 5.0
    assert "Hole diameter defaulted to 5 mm." in parsed.intent.assumptions


def test_missing_units_defaults_to_mm() -> None:
    parsed = parse_prompt("Make a bracket width 120 height 60 with two screw holes and center cutout.")

    assert parsed.parameter_table.get("back_plate_width_mm").unit == "mm"
    assert "Units assumed to be millimeters." in parsed.intent.assumptions


def test_missing_hole_spacing_derives_from_width_minus_40() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 150 mm wide with two screw holes and a center cutout.")

    assert _value(parsed, "mounting_hole_spacing_mm") == 110.0
    assert "Hole spacing defaulted to width - 40 mm." in parsed.intent.assumptions


def test_prompt_without_cutout_does_not_activate_center_cutout() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.")

    assert _is_active(parsed, "center_cutout") is False
    assert "center_cutout_width_mm" not in parsed.parameter_table.by_name()
    assert "cut_center_opening" not in _step_ids(parsed)


def test_prompt_with_center_cutout_activates_center_cutout() -> None:
    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes and a center cutout."
    )

    assert _is_active(parsed, "center_cutout") is True
    assert "center_cutout_width_mm" in parsed.parameter_table.by_name()
    assert "cut_center_opening" in _step_ids(parsed)


def test_prompt_without_rounded_corners_does_not_force_rounded_corners() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.")

    assert _is_active(parsed, "rounded_corners") is False
    assert "corner_radius_mm" not in parsed.parameter_table.by_name()
    assert parsed.feature_plan.steps[0].operation == "extrude_plate"


def test_prompt_with_rounded_corners_activates_rounded_corners() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide with rounded corners and two screw holes.")

    assert _is_active(parsed, "rounded_corners") is True
    assert "corner_radius_mm" in parsed.parameter_table.by_name()
    assert parsed.feature_plan.steps[0].operation == "extrude_rounded_plate"


def test_public_feature_planner_omits_inactive_cutout() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.")

    plan = plan_wall_bracket_features(parsed.parameter_table)

    assert "cut_center_opening" not in {step.id for step in plan.steps}


def test_missing_material_and_load_requirement_are_unknowns() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket with two screw holes and a center cutout.")

    assert "material" in parsed.intent.unknowns
    assert "load requirement" in parsed.intent.unknowns
    assert "Material was not specified." in parsed.intent.assumptions
    assert "Load requirement was not specified." in parsed.intent.assumptions


@pytest.mark.parametrize("prompt", [
    "Make a gear with 24 teeth.",
    "Create an enclosure for a PCB.",
    "Design a shaft coupler with two set screws.",
])
def test_unsupported_objects_are_rejected(prompt: str) -> None:
    with pytest.raises(UnsupportedObjectError, match="Unsupported object type"):
        parse_prompt(prompt)


def test_parse_command_writes_parsed_outputs() -> None:
    before = _run_dirs()

    result = main([
        "parse",
        "Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.",
    ])
    new_runs = _new_run_dirs(before)

    assert result == 0
    assert len(new_runs) == 1
    assert (PROJECT_ROOT / "output" / "parsed_intent.json").exists()
    assert (PROJECT_ROOT / "output" / "parsed_params.yaml").exists()
    assert (PROJECT_ROOT / "output" / "parsed_constraints.json").exists()
    assert (PROJECT_ROOT / "output" / "parsed_feature_plan.json").exists()
    assert (PROJECT_ROOT / "output" / "parsed" / "parsed_intent.json").exists()

    params = yaml.safe_load((PROJECT_ROOT / "output" / "parsed_params.yaml").read_text())
    assert params["family"] == "wall_mounted_bracket"
    assert params["metadata"]["feature_flags"]["center_cutout"]["state"] == "omitted"
    assert "center_cutout_width_mm" not in {parameter["name"] for parameter in params["parameters"]}

    run_dir = new_runs[0]
    assert (run_dir / "parsed_intent.json").exists()
    assert (run_dir / "parsed_params.yaml").exists()
    assert (run_dir / "parsed_constraints.json").exists()
    assert (run_dir / "parsed_feature_plan.json").exists()
    assert (run_dir / "prompt.txt").read_text(encoding="utf-8").strip().startswith("Make a wall-mounted bracket")
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["run_id"] == run_dir.name
    assert metadata["command_type"] == "parse"
    assert metadata["object_type"] == "wall_mounted_bracket"
    assert "mounting_holes" in metadata["active_features"]
    assert "center_cutout" in metadata["omitted_features"]


def test_parse_build_exports_real_cad_and_validation_report() -> None:
    _require_cadquery()
    before = _run_dirs()

    result = main([
        "parse-build",
        "Make a wall-mounted bracket 150 mm wide, 80 mm tall, 10 mm thick, "
        "with two 6 mm screw holes and a center cutout.",
    ])
    new_runs = _new_run_dirs(before)

    step_path = PROJECT_ROOT / "output" / "parsed_bracket.step"
    stl_path = PROJECT_ROOT / "output" / "parsed_bracket.stl"
    report_path = PROJECT_ROOT / "output" / "parsed_validation_report.json"
    assert result == 0
    assert len(new_runs) == 1
    assert step_path.exists() and step_path.stat().st_size > 0
    assert stl_path.exists() and stl_path.stat().st_size > 0
    assert report_path.exists()

    run_dir = new_runs[0]
    persistent_step = run_dir / "parsed_bracket.step"
    persistent_stl = run_dir / "parsed_bracket.stl"
    persistent_report = run_dir / "parsed_validation_report.json"
    assert persistent_step.exists() and persistent_step.stat().st_size > 0
    assert persistent_stl.exists() and persistent_stl.stat().st_size > 0
    assert persistent_report.exists()
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["validation_valid"] is True
    assert "center_cutout" in metadata["active_features"]
    assert "rounded_corners" in metadata["omitted_features"]


def test_parse_build_twice_creates_distinct_persistent_runs_without_overwriting_first() -> None:
    _require_cadquery()
    before = _run_dirs()
    prompt = "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes."

    assert main(["parse-build", prompt]) == 0
    first_runs = _new_run_dirs(before)
    assert len(first_runs) == 1
    first_run = first_runs[0]
    first_step = first_run / "parsed_bracket.step"
    first_stl = first_run / "parsed_bracket.stl"
    first_step_bytes = first_step.read_bytes()
    first_stl_bytes = first_stl.read_bytes()

    assert main(["parse-build", prompt]) == 0
    second_runs = _new_run_dirs(before)
    assert len(second_runs) == 2
    assert len({run.name for run in second_runs}) == 2

    assert first_step.read_bytes() == first_step_bytes
    assert first_stl.read_bytes() == first_stl_bytes


def test_parse_build_without_cutout_writes_feature_plan_without_cutout() -> None:
    _require_cadquery()

    result = main([
        "parse-build",
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
    ])

    plan = yaml.safe_load((PROJECT_ROOT / "output" / "parsed_feature_plan.json").read_text())
    assert result == 0
    assert "cut_center_opening" not in {step["id"] for step in plan["steps"]}


def test_parse_build_with_cutout_writes_feature_plan_with_cutout() -> None:
    _require_cadquery()

    result = main([
        "parse-build",
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, "
        "with two screw holes and a center cutout.",
    ])

    plan = yaml.safe_load((PROJECT_ROOT / "output" / "parsed_feature_plan.json").read_text())
    assert result == 0
    assert "cut_center_opening" in {step["id"] for step in plan["steps"]}
