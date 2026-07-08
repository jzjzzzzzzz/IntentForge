import json
from pathlib import Path

import pytest
import yaml

from intentforge.editor.edit_intent_handler import apply_edit_request
from intentforge.cli import main
from intentforge.features import feature_flags_for_parameter_table, is_feature_active
from intentforge.parser import parse_prompt
from intentforge.parser.edit_parser import UnsupportedEditError, parse_edit_request
from intentforge.schemas import ParameterTable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def _run_dirs() -> set[Path]:
    runs_dir = PROJECT_ROOT / "output" / "edit_parse_runs"
    if not runs_dir.exists():
        return set()
    return {path for path in runs_dir.iterdir() if path.is_dir()}


def _new_run_dirs(before: set[Path]) -> list[Path]:
    return sorted(_run_dirs() - before, key=lambda path: path.name)


def _latest_updated_table() -> ParameterTable:
    return ParameterTable.model_validate(yaml.safe_load((PROJECT_ROOT / "output" / "updated_params.yaml").read_text()))


def _edits(parsed: dict) -> list[tuple[str, str, float | None]]:
    normalized = []
    for edit in parsed["edits"]:
        normalized.append((edit["type"], edit.get("parameter") or edit.get("feature"), edit.get("value")))
    return normalized


def test_parses_width_edit() -> None:
    parsed = parse_edit_request("Make it 150 mm wide.")

    assert ("set_parameter", "width", 150.0) in _edits(parsed)


def test_parses_height_edit() -> None:
    parsed = parse_edit_request("Set height to 80 mm.")

    assert ("set_parameter", "height", 80.0) in _edits(parsed)


def test_parses_thickness_edit() -> None:
    parsed = parse_edit_request("Make it 10 mm thick.")

    assert ("set_parameter", "thickness", 10.0) in _edits(parsed)


def test_parses_hole_diameter_edit() -> None:
    parsed = parse_edit_request("Change the hole diameter to 6 mm.")

    assert ("set_parameter", "hole_diameter", 6.0) in _edits(parsed)


def test_parses_hole_spacing_edit() -> None:
    parsed = parse_edit_request("Set hole spacing to 100 mm.")

    assert ("set_parameter", "hole_spacing", 100.0) in _edits(parsed)


def test_parses_four_hole_spacing_xy_edit() -> None:
    parsed = parse_edit_request("Use four holes spaced 100 mm by 50 mm.")

    assert ("set_parameter", "hole_count", 4.0) in _edits(parsed)
    assert ("set_parameter", "hole_spacing_x", 100.0) in _edits(parsed)
    assert ("set_parameter", "hole_spacing_y", 50.0) in _edits(parsed)


def test_parses_cutout_size_edit() -> None:
    parsed = parse_edit_request("Make the cutout 40 mm wide and 20 mm tall.")

    assert ("set_parameter", "cutout_width", 40.0) in _edits(parsed)
    assert ("set_parameter", "cutout_height", 20.0) in _edits(parsed)
    assert ("set_parameter", "width", 40.0) not in _edits(parsed)


def test_parses_keep_thickness() -> None:
    parsed = parse_edit_request("Make it 150 mm wide but keep the same thickness.")

    assert ("set_parameter", "width", 150.0) in _edits(parsed)
    assert parsed["preserve"] == ["thickness"]


def test_parses_preserve_symmetry() -> None:
    parsed = parse_edit_request("Increase hole spacing to 100 mm while preserving symmetry.")

    assert ("set_parameter", "hole_spacing", 100.0) in _edits(parsed)
    assert "mounting_hole_symmetry" in parsed["preserve"]


def test_parses_remove_center_cutout() -> None:
    parsed = parse_edit_request("Remove the center cutout.")

    assert ("disable_feature", "center_cutout", None) in _edits(parsed)


def test_parses_add_center_cutout() -> None:
    parsed = parse_edit_request("Add a center cutout.")

    assert ("enable_feature", "center_cutout", None) in _edits(parsed)


def test_parses_add_center_cutout_with_dimensions() -> None:
    parsed = parse_edit_request("Add a 40 mm by 20 mm center cutout.")

    assert ("enable_feature", "center_cutout", None) in _edits(parsed)
    assert ("set_parameter", "cutout_width", 40.0) in _edits(parsed)
    assert ("set_parameter", "cutout_height", 20.0) in _edits(parsed)


def test_parses_add_rounded_corners() -> None:
    parsed = parse_edit_request("Add rounded corners.")

    assert ("enable_feature", "rounded_corners", None) in _edits(parsed)


def test_parses_remove_rounded_corners() -> None:
    parsed = parse_edit_request("Remove rounded corners.")

    assert ("disable_feature", "rounded_corners", None) in _edits(parsed)


def test_rejects_vague_edit() -> None:
    with pytest.raises(UnsupportedEditError, match="measurable"):
        parse_edit_request("Make it better.")


def test_rejects_unsupported_object_edit() -> None:
    with pytest.raises(UnsupportedEditError, match="Unsupported object"):
        parse_edit_request("Turn it into a gear.")


def test_parses_change_to_four_mounting_holes() -> None:
    parsed = parse_edit_request("Change it to four mounting holes.")

    assert ("enable_feature", "mounting_holes", None) in _edits(parsed)
    assert ("set_parameter", "hole_count", 4.0) in _edits(parsed)


def test_parses_change_to_two_mounting_holes() -> None:
    parsed = parse_edit_request("Change it to two mounting holes.")

    assert ("enable_feature", "mounting_holes", None) in _edits(parsed)
    assert ("set_parameter", "hole_count", 2.0) in _edits(parsed)


def test_parses_remove_mounting_holes() -> None:
    parsed = parse_edit_request("Remove the mounting holes.")

    assert ("disable_feature", "mounting_holes", None) in _edits(parsed)


def test_rejects_unsupported_three_holes() -> None:
    with pytest.raises(UnsupportedEditError, match="two or four holes"):
        parse_edit_request("Add three mounting holes.")


def test_apply_change_to_four_mounting_holes_is_accepted() -> None:
    _require_cadquery()
    table = ParameterTable.model_validate(yaml.safe_load((PROJECT_ROOT / "examples" / "bracket_params.yaml").read_text()))
    parsed = parse_edit_request("Change it to four mounting holes.")
    report = apply_edit_request(table, parsed)
    updated_table = ParameterTable.model_validate(report.metadata["updated_parameter_table"])
    flags = feature_flags_for_parameter_table(updated_table)

    assert ("set_parameter", "hole_count", 4.0) in _edits(parsed)
    assert report.accepted is True
    assert updated_table.get("mounting_hole_count").value == 4.0
    assert updated_table.get("mounting_hole_spacing_x_mm").value == 44.0
    assert updated_table.get("mounting_hole_spacing_y_mm").value == 50.0
    assert flags["mounting_holes"]["pattern"] == "rectangular_4"


def test_apply_change_from_four_to_two_mounting_holes_is_accepted() -> None:
    _require_cadquery()
    parsed_design = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide, 80 mm tall, with four holes spaced 90 mm by 40 mm."
    )
    parsed_edit = parse_edit_request("Change it to two mounting holes.")
    report = apply_edit_request(parsed_design.parameter_table, parsed_edit, parsed_design.constraint_graph)
    updated_table = ParameterTable.model_validate(report.metadata["updated_parameter_table"])
    flags = feature_flags_for_parameter_table(updated_table)

    assert report.accepted is True
    assert updated_table.get("mounting_hole_count").value == 2.0
    assert updated_table.get("mounting_hole_diameter_mm").value == parsed_design.parameter_table.get("mounting_hole_diameter_mm").value
    assert updated_table.get("mounting_hole_spacing_x_mm").value == 90.0
    assert flags["mounting_holes"]["pattern"] == "symmetric_2_horizontal"


def test_edit_parse_command_writes_latest_and_persistent_outputs() -> None:
    before = _run_dirs()

    result = main(["edit-parse", "Make it 150 mm wide but keep the same thickness."])
    new_runs = _new_run_dirs(before)

    assert result == 0
    assert len(new_runs) == 1
    assert (PROJECT_ROOT / "output" / "parsed_edit.json").exists()
    assert (new_runs[0] / "parsed_edit.json").exists()
    assert (new_runs[0] / "prompt.txt").exists()
    metadata = json.loads((new_runs[0] / "run_metadata.json").read_text())
    assert metadata["command_type"] == "edit-parse"
    assert metadata["accepted"] is True
    assert metadata["parsed_edits"][0]["parameter"] == "width"


def test_edit_parse_apply_width_edit_is_accepted_and_preserves_thickness() -> None:
    _require_cadquery()
    before = _run_dirs()

    result = main(["edit-parse-apply", "bracket", "Make it 150 mm wide but keep the same thickness."])
    new_runs = _new_run_dirs(before)
    updated_table = _latest_updated_table()
    report = json.loads((PROJECT_ROOT / "output" / "edit_report.json").read_text())

    assert result == 0
    assert len(new_runs) == 1
    assert report["accepted"] is True
    assert updated_table.get("back_plate_width_mm").value == 150.0
    assert updated_table.get("back_plate_thickness_mm").value == 6.0
    assert (new_runs[0] / "bracket_edited.step").stat().st_size > 0
    assert (new_runs[0] / "bracket_edited.stl").stat().st_size > 0


def test_remove_center_cutout_omits_center_cutout_feature() -> None:
    _require_cadquery()

    result = main(["edit-parse-apply", "bracket", "Remove the center cutout."])
    updated_table = _latest_updated_table()
    flags = feature_flags_for_parameter_table(updated_table)

    assert result == 0
    assert flags["center_cutout"]["state"] == "omitted"


def test_add_center_cutout_activates_center_cutout_feature() -> None:
    _require_cadquery()

    result = main(["edit-parse-apply", "bracket", "Add a center cutout."])
    updated_table = _latest_updated_table()
    flags = feature_flags_for_parameter_table(updated_table)

    assert result == 0
    assert is_feature_active(flags, "center_cutout") is True


def test_add_center_cutout_with_dimensions_validates() -> None:
    _require_cadquery()

    result = main(["edit-parse-apply", "bracket", "Add a 40 mm by 20 mm center cutout."])
    updated_table = _latest_updated_table()
    validation_report = json.loads((PROJECT_ROOT / "output" / "edited_validation_report.json").read_text())

    assert result == 0
    assert updated_table.get("center_cutout_width_mm").value == 40.0
    assert updated_table.get("center_cutout_height_mm").value == 20.0
    assert validation_report["valid"] is True


def test_edit_parse_apply_change_to_four_mounting_holes_exports_valid_model() -> None:
    _require_cadquery()
    before = _run_dirs()

    result = main(["edit-parse-apply", "bracket", "Change it to four mounting holes."])
    new_runs = _new_run_dirs(before)
    updated_table = _latest_updated_table()
    flags = feature_flags_for_parameter_table(updated_table)
    validation_report = json.loads((PROJECT_ROOT / "output" / "edited_validation_report.json").read_text())

    assert result == 0
    assert len(new_runs) == 1
    assert updated_table.get("mounting_hole_count").value == 4.0
    assert updated_table.get("mounting_hole_spacing_x_mm").value == 44.0
    assert updated_table.get("mounting_hole_spacing_y_mm").value == 50.0
    assert flags["mounting_holes"]["pattern"] == "rectangular_4"
    assert validation_report["valid"] is True
    assert (new_runs[0] / "bracket_edited.step").stat().st_size > 0
    assert (new_runs[0] / "bracket_edited.stl").stat().st_size > 0


def test_edit_parse_apply_remove_mounting_holes_is_accepted_and_validates() -> None:
    _require_cadquery()

    result = main(["edit-parse-apply", "bracket", "Remove the mounting holes."])
    updated_table = _latest_updated_table()
    flags = feature_flags_for_parameter_table(updated_table)
    validation_report = json.loads((PROJECT_ROOT / "output" / "edited_validation_report.json").read_text())

    assert result == 0
    assert flags["mounting_holes"]["state"] == "omitted"
    assert flags["mounting_holes"]["pattern"] == "none"
    assert validation_report["valid"] is True


def test_unsupported_hole_count_edit_does_not_export_cad() -> None:
    _require_cadquery()

    assert main(["edit-parse-apply", "bracket", "Change it to four mounting holes."]) == 0
    latest_step = PROJECT_ROOT / "output" / "bracket_edited.step"
    latest_stl = PROJECT_ROOT / "output" / "bracket_edited.stl"
    step_before = latest_step.read_bytes()
    stl_before = latest_stl.read_bytes()
    before = _run_dirs()

    result = main(["edit-parse-apply", "bracket", "Change it to three mounting holes."])
    new_runs = _new_run_dirs(before)

    assert result == 1
    assert latest_step.read_bytes() == step_before
    assert latest_stl.read_bytes() == stl_before
    assert len(new_runs) == 1
    assert not (new_runs[0] / "bracket_edited.step").exists()
    metadata = json.loads((new_runs[0] / "run_metadata.json").read_text())
    assert metadata["accepted"] is False


def test_edit_to_omitted_cutout_parameter_is_rejected_unless_enabled() -> None:
    _require_cadquery()

    assert main(["edit-parse-apply", "bracket", "Remove the center cutout."]) == 0
    removed_table = _latest_updated_table()
    parsed = parse_edit_request("Make the cutout 40 mm wide and 20 mm tall.")

    from intentforge.editor.edit_intent_handler import apply_edit_request

    report = apply_edit_request(removed_table, parsed)

    assert report.accepted is False
    assert "center_cutout is omitted" in report.rejected_edits[0]["reason"]


def test_invalid_natural_language_edit_does_not_export_cad() -> None:
    _require_cadquery()

    assert main(["edit-parse-apply", "bracket", "Make it 150 mm wide."]) == 0
    latest_step = PROJECT_ROOT / "output" / "bracket_edited.step"
    latest_stl = PROJECT_ROOT / "output" / "bracket_edited.stl"
    step_before = latest_step.read_bytes()
    stl_before = latest_stl.read_bytes()
    before = _run_dirs()

    result = main(["edit-parse-apply", "bracket", "Make it better."])
    new_runs = _new_run_dirs(before)

    assert result == 1
    assert latest_step.read_bytes() == step_before
    assert latest_stl.read_bytes() == stl_before
    assert len(new_runs) == 1
    assert not (new_runs[0] / "bracket_edited.step").exists()
    metadata = json.loads((new_runs[0] / "run_metadata.json").read_text())
    assert metadata["accepted"] is False


def test_repeated_edit_parse_apply_runs_do_not_overwrite_persistent_outputs() -> None:
    _require_cadquery()
    before = _run_dirs()

    assert main(["edit-parse-apply", "bracket", "Make it 150 mm wide."]) == 0
    first_runs = _new_run_dirs(before)
    assert len(first_runs) == 1
    first_run = first_runs[0]
    first_step = first_run / "bracket_edited.step"
    first_bytes = first_step.read_bytes()

    assert main(["edit-parse-apply", "bracket", "Make it 150 mm wide."]) == 0
    all_new_runs = _new_run_dirs(before)

    assert len(all_new_runs) == 2
    assert len({run.name for run in all_new_runs}) == 2
    assert first_step.read_bytes() == first_bytes
