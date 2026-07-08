import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from intentforge.cli import main
from intentforge.editor.edit_intent_handler import apply_edit_request, write_edit_report
from intentforge.features import feature_flags_for_parameter_table, is_feature_active
from intentforge.parameters.aliases import canonical_parameter_name
from intentforge.parser import parse_prompt
from intentforge.schemas import EditReport, EditRequest, ValidationCheck, ValidationReport
from intentforge.schemas import ConstraintGraph, ParameterTable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = PROJECT_ROOT / "examples"


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def _load_parameter_table() -> ParameterTable:
    return ParameterTable.model_validate(yaml.safe_load((EXAMPLES_DIR / "bracket_params.yaml").read_text()))


def _load_constraints() -> ConstraintGraph:
    return ConstraintGraph.model_validate(json.loads((EXAMPLES_DIR / "bracket_constraints.json").read_text()))


def _load_edit(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / name).read_text())


def _preserved_value(report, parameter: str):
    preserved = {item["parameter"]: item["preserved_value"] for item in report.preserved_parameters}
    return preserved[parameter]


def _updated_table(report) -> ParameterTable:
    return ParameterTable.model_validate(report.metadata["updated_parameter_table"])


def _write_edit_file(path: Path, edit_data: dict) -> Path:
    path.write_text(json.dumps(edit_data), encoding="utf-8")
    return path


def _remove_if_exists(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def test_edit_request_requires_a_requested_change() -> None:
    with pytest.raises(ValidationError):
        EditRequest(family="wall_mounted_bracket")


def test_edit_request_captures_parameter_update_and_preserved_intent() -> None:
    request = EditRequest(
        family="wall_mounted_bracket",
        change_request="Increase the support arm length to 125 mm.",
        parameter_updates={"support_arm_length_mm": 125.0},
        preserve_intent=["Keep the mounting hole pattern symmetric."],
    )

    assert request.parameter_updates["support_arm_length_mm"] == 125.0
    assert request.preserve_intent == ["Keep the mounting hole pattern symmetric."]


def test_edit_report_can_embed_validation_report() -> None:
    validation_report = ValidationReport(
        family="wall_mounted_bracket",
        checks=[
            ValidationCheck(
                id="support_arm_dimensions",
                description="Support arm dimensions match edited parameters.",
                status="pass",
            )
        ],
    )

    report = EditReport(
        family="wall_mounted_bracket",
        target_model_id="bracket-v1",
        accepted=True,
        changes_applied=["support_arm_length_mm updated to 125.0"],
        updated_parameters={"support_arm_length_mm": 125.0},
        validation_report=validation_report,
    )

    assert report.accepted is True
    assert report.validation_report is not None
    assert report.validation_report.passed is True


def test_width_edit_preserves_thickness_and_hole_diameter() -> None:
    _require_cadquery()

    report = apply_edit_request(_load_parameter_table(), _load_edit("edit_width.json"), _load_constraints())

    assert report.accepted is True
    assert report.updated_parameters["back_plate_width_mm"] == 150.0
    assert _preserved_value(report, "back_plate_thickness_mm") == 6.0
    assert _preserved_value(report, "mounting_hole_diameter_mm") == 6.5
    assert report.changed_parameters[0]["requested_parameter"] == "width"
    assert report.changed_parameters[0]["canonical_parameter"] == "back_plate_width_mm"


def test_hole_spacing_edit_preserves_symmetry_intent() -> None:
    _require_cadquery()

    report = apply_edit_request(
        _load_parameter_table(),
        _load_edit("edit_hole_spacing.json"),
        _load_constraints(),
    )

    assert report.accepted is True
    assert report.updated_parameters["mounting_hole_spacing_mm"] == 100.0
    assert _preserved_value(report, "mounting_hole_symmetry") is True


def test_accepted_edit_regenerates_valid_model() -> None:
    _require_cadquery()

    report = apply_edit_request(_load_parameter_table(), _load_edit("edit_width.json"), _load_constraints())

    assert report.accepted is True
    assert report.validation_report is not None
    assert report.validation_report.valid is True


def test_accepted_edit_writes_updated_params_and_edit_report() -> None:
    _require_cadquery()

    result = main(["edit-example", "bracket", "examples/edit_width.json"])
    updated_params_path = PROJECT_ROOT / "output" / "updated_params.yaml"
    edit_report_path = PROJECT_ROOT / "output" / "edit_report.json"

    assert result == 0
    assert updated_params_path.exists()
    assert edit_report_path.exists()
    updated_params = yaml.safe_load(updated_params_path.read_text())
    edit_report = json.loads(edit_report_path.read_text())
    assert updated_params["family"] == "wall_mounted_bracket"
    assert edit_report["accepted"] is True
    assert (PROJECT_ROOT / "output" / "edit_reports" / "edit_width_edit_report.json").exists()
    assert (PROJECT_ROOT / "output" / "edited_models" / "edit_width_bracket.step").exists()
    assert (PROJECT_ROOT / "output" / "edited_models" / "edit_width_bracket.stl").exists()


@pytest.mark.parametrize(
    ("edit_data", "expected_failure"),
    [
        (
            {"edits": [{"type": "set_parameter", "parameter": "width", "value": -10}]},
            "negative width",
        ),
        (
            {"edits": [{"type": "set_parameter", "parameter": "hole_diameter", "value": 80}]},
            "invalid hole diameter",
        ),
        (
            {"edits": [{"type": "set_parameter", "parameter": "hole_spacing", "value": 120}]},
            "invalid hole spacing",
        ),
        (
            {"edits": [{"type": "set_parameter", "parameter": "hole_count", "value": 3}]},
            "unsupported hole count",
        ),
        (
            {"edits": [{"type": "set_parameter", "parameter": "cutout_width", "value": 118}]},
            "oversized cutout",
        ),
        (
            {"edits": [{"type": "set_parameter", "parameter": "does_not_exist", "value": 10}]},
            "non-existent parameter",
        ),
        (
            {"edits": [{"type": "set_parameter", "parameter": "width", "value": "large"}]},
            "non-number value",
        ),
    ],
)
def test_invalid_edits_are_rejected(edit_data: dict, expected_failure: str) -> None:
    report = apply_edit_request(_load_parameter_table(), edit_data, _load_constraints())

    combined_reasons = " ".join(
        [
            *report.failed_constraints,
            *[item["reason"] for item in report.rejected_edits],
            report.human_readable_explanation,
        ]
    )
    assert report.accepted is False
    assert expected_failure in combined_reasons


def test_edited_model_does_not_export_if_edit_is_rejected() -> None:
    report = apply_edit_request(
        _load_parameter_table(),
        {"edits": [{"type": "set_parameter", "parameter": "hole_diameter", "value": 80}]},
        _load_constraints(),
    )

    assert report.accepted is False
    assert "updated_parameter_table" not in report.metadata


def test_edit_report_explains_changed_and_preserved_parameters(tmp_path) -> None:
    _require_cadquery()

    report = apply_edit_request(_load_parameter_table(), _load_edit("edit_width.json"), _load_constraints())
    report_path = write_edit_report(report, tmp_path / "edit_report.json")
    report_data = json.loads(report_path.read_text())

    assert report_data["changed_parameters"][0]["parameter"] == "back_plate_width_mm"
    assert report_data["changed_parameters"][0]["requested_parameter"] == "width"
    assert report_data["changed_parameters"][0]["canonical_parameter"] == "back_plate_width_mm"
    assert report_data["changed_parameters"][0]["old_value"] == 120.0
    assert report_data["changed_parameters"][0]["new_value"] == 150.0
    assert "back_plate_thickness_mm" in {
        item["parameter"] for item in report_data["preserved_parameters"]
    }
    assert report_data["human_readable_explanation"]


def test_editing_width_preserves_omitted_center_cutout_state() -> None:
    _require_cadquery()

    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.")
    report = apply_edit_request(
        parsed.parameter_table,
        {"edits": [{"type": "set_parameter", "parameter": "width", "value": 150}]},
        parsed.constraint_graph,
    )
    updated_table = _updated_table(report)
    flags = feature_flags_for_parameter_table(updated_table)

    assert report.accepted is True
    assert flags["center_cutout"]["state"] == "omitted"
    assert "center_cutout_width_mm" not in updated_table.by_name()


def test_editing_cutout_width_is_rejected_when_center_cutout_omitted() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.")

    report = apply_edit_request(
        parsed.parameter_table,
        {"edits": [{"type": "set_parameter", "parameter": "cutout_width", "value": 30}]},
        parsed.constraint_graph,
    )

    assert report.accepted is False
    assert "center_cutout is omitted" in report.rejected_edits[0]["reason"]


def test_enabling_center_cutout_and_setting_dimensions_is_accepted() -> None:
    _require_cadquery()

    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.")
    report = apply_edit_request(
        parsed.parameter_table,
        {
            "edits": [
                {"type": "set_parameter", "parameter": "cutout_width", "value": 30},
                {"type": "enable_feature", "feature": "center_cutout"},
                {"type": "set_parameter", "parameter": "cutout_height", "value": 15},
            ]
        },
        parsed.constraint_graph,
    )
    updated_table = _updated_table(report)
    flags = feature_flags_for_parameter_table(updated_table)

    assert report.accepted is True
    assert is_feature_active(flags, "center_cutout") is True
    assert updated_table.get("center_cutout_width_mm").value == 30.0
    assert updated_table.get("center_cutout_height_mm").value == 15.0
    assert report.validation_report is not None
    assert report.validation_report.valid is True


def test_changing_two_holes_to_four_holes_adds_rectangular_spacing_and_validates() -> None:
    _require_cadquery()

    report = apply_edit_request(
        _load_parameter_table(),
        {
            "edits": [
                {"type": "enable_feature", "feature": "mounting_holes"},
                {"type": "set_parameter", "parameter": "hole_count", "value": 4},
            ]
        },
        _load_constraints(),
    )
    updated_table = _updated_table(report)
    flags = feature_flags_for_parameter_table(updated_table)

    assert report.accepted is True
    assert updated_table.get("mounting_hole_count").value == 4.0
    assert updated_table.get("mounting_hole_diameter_mm").value == 6.5
    assert updated_table.get("mounting_hole_spacing_x_mm").value == 44.0
    assert updated_table.get("mounting_hole_spacing_y_mm").value == 50.0
    assert flags["mounting_holes"]["pattern"] == "rectangular_4"
    assert report.validation_report is not None
    assert report.validation_report.valid is True


def test_removing_mounting_holes_omits_hole_validation() -> None:
    _require_cadquery()

    report = apply_edit_request(
        _load_parameter_table(),
        {"edits": [{"type": "disable_feature", "feature": "mounting_holes"}]},
        _load_constraints(),
    )
    updated_table = _updated_table(report)
    flags = feature_flags_for_parameter_table(updated_table)

    assert report.accepted is True
    assert flags["mounting_holes"]["state"] == "omitted"
    assert flags["mounting_holes"]["pattern"] == "none"
    assert report.validation_report is not None
    assert report.validation_report.valid is True


def test_width_alias_maps_to_canonical_width_parameter() -> None:
    assert canonical_parameter_name("width") == "back_plate_width_mm"
    assert canonical_parameter_name("back_plate_width_mm") == "back_plate_width_mm"


def test_hole_spacing_aliases_map_to_canonical_pattern_parameters() -> None:
    assert canonical_parameter_name("hole_spacing") == "mounting_hole_spacing_mm"
    assert canonical_parameter_name("hole_spacing_x") == "mounting_hole_spacing_x_mm"
    assert canonical_parameter_name("hole_spacing_y") == "mounting_hole_spacing_y_mm"


def test_unknown_alias_is_rejected() -> None:
    report = apply_edit_request(
        _load_parameter_table(),
        {"edits": [{"type": "set_parameter", "parameter": "unknown_width", "value": 150}]},
        _load_constraints(),
    )

    assert report.accepted is False
    assert report.rejected_edits[0]["parameter"] == "unknown_width"
    assert "non-existent parameter" in report.rejected_edits[0]["reason"]


def test_persistent_edit_reports_and_edited_models_are_created(tmp_path) -> None:
    _require_cadquery()

    edit_path = _write_edit_file(
        tmp_path / "phase45_width.json",
        {"edits": [{"type": "set_parameter", "parameter": "width", "value": 150}]},
    )
    latest_report = PROJECT_ROOT / "output" / "edit_report.json"
    persistent_report = PROJECT_ROOT / "output" / "edit_reports" / "phase45_width_edit_report.json"
    latest_step = PROJECT_ROOT / "output" / "bracket_edited.step"
    latest_stl = PROJECT_ROOT / "output" / "bracket_edited.stl"
    persistent_step = PROJECT_ROOT / "output" / "edited_models" / "phase45_width_bracket.step"
    persistent_stl = PROJECT_ROOT / "output" / "edited_models" / "phase45_width_bracket.stl"
    _remove_if_exists(persistent_report, persistent_step, persistent_stl)

    result = main(["edit-example", "bracket", str(edit_path)])

    assert result == 0
    assert latest_report.exists()
    assert persistent_report.exists()
    assert latest_step.exists() and latest_step.stat().st_size > 0
    assert latest_stl.exists() and latest_stl.stat().st_size > 0
    assert persistent_step.exists() and persistent_step.stat().st_size > 0
    assert persistent_stl.exists() and persistent_stl.stat().st_size > 0


def test_rejected_edit_writes_reports_but_no_persistent_cad(tmp_path) -> None:
    _require_cadquery()

    edit_path = _write_edit_file(
        tmp_path / "phase45_invalid_hole.json",
        {"edits": [{"type": "set_parameter", "parameter": "hole_diameter", "value": 80}]},
    )
    latest_report = PROJECT_ROOT / "output" / "edit_report.json"
    persistent_report = PROJECT_ROOT / "output" / "edit_reports" / "phase45_invalid_hole_edit_report.json"
    persistent_step = PROJECT_ROOT / "output" / "edited_models" / "phase45_invalid_hole_bracket.step"
    persistent_stl = PROJECT_ROOT / "output" / "edited_models" / "phase45_invalid_hole_bracket.stl"
    _remove_if_exists(persistent_report, persistent_step, persistent_stl)

    result = main(["edit-example", "bracket", str(edit_path)])

    assert result == 1
    assert latest_report.exists()
    assert persistent_report.exists()
    assert json.loads(latest_report.read_text())["accepted"] is False
    assert not persistent_step.exists()
    assert not persistent_stl.exists()


def test_invalid_edit_does_not_overwrite_latest_valid_edited_cad(tmp_path) -> None:
    _require_cadquery()

    valid_edit_path = _write_edit_file(
        tmp_path / "phase45_stale_width.json",
        {"edits": [{"type": "set_parameter", "parameter": "width", "value": 150}]},
    )
    invalid_edit_path = _write_edit_file(
        tmp_path / "phase45_stale_invalid_hole.json",
        {"edits": [{"type": "set_parameter", "parameter": "hole_diameter", "value": 80}]},
    )
    latest_step = PROJECT_ROOT / "output" / "bracket_edited.step"
    latest_stl = PROJECT_ROOT / "output" / "bracket_edited.stl"
    invalid_persistent_step = (
        PROJECT_ROOT / "output" / "edited_models" / "phase45_stale_invalid_hole_bracket.step"
    )
    invalid_persistent_stl = (
        PROJECT_ROOT / "output" / "edited_models" / "phase45_stale_invalid_hole_bracket.stl"
    )
    _remove_if_exists(invalid_persistent_step, invalid_persistent_stl)

    assert main(["edit-example", "bracket", str(valid_edit_path)]) == 0
    step_before = latest_step.read_bytes()
    stl_before = latest_stl.read_bytes()

    assert main(["edit-example", "bracket", str(invalid_edit_path)]) == 1

    assert latest_step.read_bytes() == step_before
    assert latest_stl.read_bytes() == stl_before
    assert not invalid_persistent_step.exists()
    assert not invalid_persistent_stl.exists()
