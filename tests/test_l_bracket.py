from pathlib import Path
import json

import pytest

from intentforge.editor.edit_intent_handler import apply_edit_request
from intentforge.features import feature_flags_for_parameter_table, is_feature_active
from intentforge.generator.cadquery_generator import build_l_bracket, export_model
from intentforge.parser import UnsupportedObjectError, parse_edit_request, parse_prompt
from intentforge.schemas import ParameterTable
from intentforge.validator.geometry_validator import validate_l_bracket
from intentforge.workflows import edit_parse_apply_workflow, parse_build_workflow


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def _value(table: ParameterTable, name: str):
    return table.get(name).value


def _with_value(table: ParameterTable, name: str, value):
    parameters = [
        parameter.model_copy(update={"value": value}) if parameter.name == name else parameter
        for parameter in table.parameters
    ]
    return table.model_copy(update={"parameters": parameters})


def _active(table: ParameterTable, feature: str) -> bool:
    return is_feature_active(feature_flags_for_parameter_table(table), feature)


def test_wall_mounted_bracket_parse_build_regression(tmp_path: Path) -> None:
    _require_cadquery()
    result = parse_build_workflow(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
        tmp_path,
    )

    assert result["object_type"] == "wall_mounted_bracket"
    assert result["validation_valid"] is True
    assert Path(result["latest_outputs"]["step"]).name == "parsed_bracket.step"
    assert Path(result["latest_outputs"]["validation_report"]).name == "parsed_validation_report.json"


def test_wall_mounted_bracket_edit_regression(tmp_path: Path) -> None:
    _require_cadquery()
    result = edit_parse_apply_workflow("bracket", "Make it 150 mm wide but keep the same thickness.", tmp_path)

    assert result["object_type"] == "wall_mounted_bracket"
    assert result["accepted"] is True
    assert result["validation_valid"] is True
    assert Path(result["latest_outputs"]["step"]).name == "bracket_edited.step"


def test_l_bracket_parser_extracts_core_dimensions() -> None:
    parsed = parse_prompt("Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, and 6 mm thick.")

    assert parsed.intent.family == "l_bracket"
    assert _value(parsed.parameter_table, "base_leg_length_mm") == 100.0
    assert _value(parsed.parameter_table, "vertical_leg_length_mm") == 80.0
    assert _value(parsed.parameter_table, "bracket_width_mm") == 40.0
    assert _value(parsed.parameter_table, "thickness_mm") == 6.0


def test_l_bracket_parser_detects_holes_no_holes_and_gusset() -> None:
    holes = parse_prompt("Create a right angle bracket with two holes on the base and two holes on the vertical face.")
    plain = parse_prompt("Make a plain L-bracket with no holes.")
    gusset = parse_prompt("Make an L-bracket with a triangular gusset.")

    assert _active(holes.parameter_table, "base_mounting_holes") is True
    assert _active(holes.parameter_table, "vertical_mounting_holes") is True
    assert _value(holes.parameter_table, "base_hole_count") == 2
    assert _value(holes.parameter_table, "vertical_hole_count") == 2
    assert _active(plain.parameter_table, "base_mounting_holes") is False
    assert _active(plain.parameter_table, "vertical_mounting_holes") is False
    assert _active(gusset.parameter_table, "triangular_gusset") is True


def test_l_bracket_parser_supports_common_family_and_face_variants() -> None:
    angle = parse_prompt("Make a 90 degree bracket with no holes.")
    face_holes = parse_prompt("Make an L bracket with two base face holes and two vertical face holes.")

    assert angle.intent.family == "l_bracket"
    assert _active(angle.parameter_table, "base_mounting_holes") is False
    assert _active(face_holes.parameter_table, "base_mounting_holes") is True
    assert _active(face_holes.parameter_table, "vertical_mounting_holes") is True


def test_l_bracket_parser_rejects_complex_unsupported_prompt() -> None:
    with pytest.raises(UnsupportedObjectError):
        parse_prompt("Make a curved L-bracket with arbitrary hole coordinates.")


def test_l_bracket_parser_rejects_adjustable_and_sheet_metal_flat_pattern() -> None:
    for prompt in [
        "Make an adjustable L-bracket.",
        "Make an L-bracket sheet metal flat pattern.",
        "Make an L-bracket with three holes on the base leg.",
    ]:
        with pytest.raises(UnsupportedObjectError):
            parse_prompt(prompt)


def test_l_bracket_builds_and_exports_step_stl(tmp_path: Path) -> None:
    _require_cadquery()
    parsed = parse_prompt("Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, and 6 mm thick.")

    model = build_l_bracket(parsed.parameter_table)
    step_path, stl_path = export_model(model, tmp_path / "l.step", tmp_path / "l.stl")

    assert step_path.exists()
    assert stl_path.exists()
    assert step_path.stat().st_size > 0
    assert stl_path.stat().st_size > 0


def test_l_bracket_bounding_box_tracks_base_vertical_and_width() -> None:
    _require_cadquery()
    parsed = parse_prompt("Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, and 6 mm thick.")
    wider = _with_value(parsed.parameter_table, "bracket_width_mm", 55.0)
    longer_base = _with_value(parsed.parameter_table, "base_leg_length_mm", 120.0)
    taller = _with_value(parsed.parameter_table, "vertical_leg_length_mm", 95.0)

    assert build_l_bracket(wider).val().BoundingBox().ylen == pytest.approx(55.0)
    assert build_l_bracket(longer_base).val().BoundingBox().xlen == pytest.approx(120.0)
    assert build_l_bracket(taller).val().BoundingBox().zlen == pytest.approx(95.0)


def test_l_bracket_generator_rejects_invalid_thickness_and_hole_count() -> None:
    _require_cadquery()
    parsed = parse_prompt("Make an L-bracket with two holes on the base.")

    with pytest.raises(ValueError, match="thickness_mm"):
        build_l_bracket(_with_value(parsed.parameter_table, "thickness_mm", -1.0))
    with pytest.raises(ValueError, match="base_hole_count"):
        build_l_bracket(_with_value(parsed.parameter_table, "base_hole_count", 3))


def test_l_bracket_validation_passes_and_catches_invalid_spacing() -> None:
    _require_cadquery()
    parsed = parse_prompt("Make an L-bracket with two holes on the base and two holes on the vertical face.")
    model = build_l_bracket(parsed.parameter_table)
    report = validate_l_bracket(model, parsed.parameter_table)

    assert report.valid is True

    bad_base_spacing = _with_value(parsed.parameter_table, "base_hole_spacing_mm", 98.0)
    bad_report = validate_l_bracket(None, bad_base_spacing)
    assert bad_report.valid is False
    assert any(check.id == "base_hole_spacing_range_check" for check in bad_report.failed_checks)


def test_l_bracket_validation_catches_invalid_fillet_and_gusset() -> None:
    inside = parse_prompt("Make an L-bracket with an inside fillet.")
    bad_inside = _with_value(inside.parameter_table, "inside_fillet_radius_mm", 20.0)
    gusset = parse_prompt("Make an L-bracket with a triangular gusset.")
    bad_gusset = _with_value(gusset.parameter_table, "gusset_height_mm", 200.0)

    assert validate_l_bracket(None, bad_inside).valid is False
    assert validate_l_bracket(None, bad_gusset).valid is False


def test_l_bracket_edit_base_leg_preserves_thickness() -> None:
    _require_cadquery()
    result = edit_parse_apply_workflow("l_bracket", "Make the base leg 120 mm long.")
    report = result["edit_report"]

    assert result["accepted"] is True
    assert result["validation_valid"] is True
    assert any(change["parameter"] == "base_leg_length_mm" for change in report["changed_parameters"])
    assert any(item["parameter"] == "thickness_mm" for item in report["preserved_parameters"])


def test_l_bracket_edit_vertical_leg_preserves_base_and_thickness() -> None:
    _require_cadquery()
    result = edit_parse_apply_workflow("l_bracket", "Make the vertical leg 100 mm tall.")
    report = result["edit_report"]

    assert result["accepted"] is True
    assert any(change["parameter"] == "vertical_leg_length_mm" for change in report["changed_parameters"])
    assert any(item["parameter"] == "base_leg_length_mm" for item in report["preserved_parameters"])
    assert any(item["parameter"] == "thickness_mm" for item in report["preserved_parameters"])


def test_l_bracket_edit_add_and_remove_features() -> None:
    _require_cadquery()
    table = parse_prompt("Make a plain L-bracket with no holes.").parameter_table

    add_base = apply_edit_request(
        table,
        {"edits": [{"type": "enable_feature", "feature": "base_mounting_holes"}], "preserve": []},
    )
    add_gusset = apply_edit_request(
        table,
        {"edits": [{"type": "enable_feature", "feature": "triangular_gusset"}], "preserve": []},
    )
    remove_vertical = edit_parse_apply_workflow("l_bracket", "Remove the vertical holes.")

    assert add_base.accepted is True
    assert add_gusset.accepted is True
    assert remove_vertical["accepted"] is True


def test_l_bracket_edit_feature_changes_are_leg_specific() -> None:
    _require_cadquery()
    plain = parse_prompt("Make a plain L-bracket with no holes.").parameter_table
    with_both = parse_prompt("Make an L-bracket with two holes on the base and two holes on the vertical face.").parameter_table

    add_base = apply_edit_request(
        plain,
        {"edits": [{"type": "enable_feature", "feature": "base_mounting_holes"}], "preserve": []},
    )
    add_vertical = apply_edit_request(
        plain,
        {"edits": [{"type": "enable_feature", "feature": "vertical_mounting_holes"}], "preserve": []},
    )
    remove_base = apply_edit_request(
        with_both,
        {"edits": [{"type": "disable_feature", "feature": "base_mounting_holes"}], "preserve": []},
    )
    remove_gusset = apply_edit_request(
        parse_prompt("Make an L-bracket with a triangular gusset.").parameter_table,
        {"edits": [{"type": "disable_feature", "feature": "triangular_gusset"}], "preserve": []},
    )

    add_base_flags = add_base.metadata["updated_feature_flags"]
    add_vertical_flags = add_vertical.metadata["updated_feature_flags"]
    remove_base_flags = remove_base.metadata["updated_feature_flags"]
    remove_gusset_flags = remove_gusset.metadata["updated_feature_flags"]

    assert add_base.accepted is True
    assert add_base_flags["base_mounting_holes"]["state"] == "requested_by_user"
    assert add_base_flags["vertical_mounting_holes"]["state"] == "omitted"
    assert add_vertical.accepted is True
    assert add_vertical_flags["base_mounting_holes"]["state"] == "omitted"
    assert add_vertical_flags["vertical_mounting_holes"]["state"] == "requested_by_user"
    assert remove_base.accepted is True
    assert remove_base_flags["base_mounting_holes"]["state"] == "omitted"
    assert remove_base_flags["vertical_mounting_holes"]["state"] == "requested_by_user"
    assert remove_gusset.accepted is True
    assert remove_gusset_flags["triangular_gusset"]["state"] == "omitted"


def test_l_bracket_natural_language_vague_edit_is_rejected() -> None:
    result = edit_parse_apply_workflow("l_bracket", "Make it better.")

    assert result["accepted"] is False
    assert result["cad_exported"] is False


def test_l_bracket_rejected_edit_writes_metadata_without_cad_export(tmp_path: Path) -> None:
    _require_cadquery()
    result = edit_parse_apply_workflow("l_bracket", "Change it to three base holes.", tmp_path)
    run_dir = Path(result["persistent_output_dir"])

    assert result["accepted"] is False
    assert result["cad_exported"] is False
    assert not (run_dir / "l_bracket_edited.step").exists()
    metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
    assert metadata["object_type"] == "l_bracket"
    assert "base_mounting_holes" in metadata["active_features"]


def test_l_bracket_edit_parser_rejects_unsupported_hole_count() -> None:
    table = parse_prompt("Make an L-bracket.").parameter_table

    with pytest.raises(Exception, match="hole count"):
        parse_edit_request("Change it to three mounting holes.", existing_params=table)


def test_l_bracket_parse_build_writes_family_specific_validation_report(tmp_path: Path) -> None:
    _require_cadquery()
    result = parse_build_workflow("Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, and 6 mm thick.", tmp_path)
    latest = result["latest_outputs"]
    persistent = result["persistent_outputs"]
    metadata = result["run_metadata"]

    assert result["validation_valid"] is True
    assert latest["validation_report"].endswith("parsed_l_bracket_validation_report.json")
    assert Path(latest["validation_report"]).exists()
    assert Path(latest["shared_validation_report"]).exists()
    assert persistent["validation_report"].endswith("parsed_l_bracket_validation_report.json")
    assert metadata["object_type"] == "l_bracket"
    assert metadata["active_features"] == ["base_leg", "vertical_leg"]


def test_l_bracket_edited_outputs_use_family_specific_validation_report(tmp_path: Path) -> None:
    _require_cadquery()
    result = edit_parse_apply_workflow("l_bracket", "Make the base leg 120 mm long.", tmp_path)
    latest = result["latest_outputs"]
    persistent = result["persistent_outputs"]
    metadata = result["run_metadata"]

    assert result["accepted"] is True
    assert latest["validation_report"].endswith("l_bracket_edited_validation_report.json")
    assert Path(latest["validation_report"]).exists()
    assert Path(latest["shared_validation_report"]).exists()
    assert persistent["validation_report"].endswith("l_bracket_edited_validation_report.json")
    assert metadata["object_type"] == "l_bracket"
    assert metadata["validation_valid"] is True
