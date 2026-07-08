import json
from pathlib import Path

import pytest

from mcp_server import tools


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def test_parse_cad_prompt_returns_ok_for_bracket_prompt() -> None:
    result = tools.parse_cad_prompt("Make a wall-mounted bracket 120 mm wide with two screw holes.")

    assert result["ok"] is True
    assert result["intent"]["family"] == "wall_mounted_bracket"
    assert result["parameters"]["family"] == "wall_mounted_bracket"
    assert result["feature_plan"]["family"] == "wall_mounted_bracket"
    assert "mounting_holes" in result["active_features"]


def test_parse_cad_prompt_rejects_unsupported_object() -> None:
    result = tools.parse_cad_prompt("Make a gear with 24 teeth.")

    assert result["ok"] is False
    assert result["error_type"] == "UnsupportedObjectError"
    assert "Unsupported object type" in result["message"]


def test_parse_build_cad_prompt_writes_persistent_output_run(tmp_path: Path) -> None:
    _require_cadquery()

    result = tools.parse_build_cad_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with four corner screw holes.",
        output_root=str(tmp_path),
    )

    assert result["ok"] is True
    assert result["validation_valid"] is True
    assert (tmp_path / "parsed_bracket.step").stat().st_size > 0
    assert (tmp_path / "parsed_bracket.stl").stat().st_size > 0
    run_dir = tmp_path / "parsed_runs" / result["run_id"]
    assert run_dir.exists()
    assert (run_dir / "parsed_bracket.step").stat().st_size > 0
    assert (run_dir / "parsed_validation_report.json").exists()


def test_parse_edit_prompt_parses_width_edit() -> None:
    result = tools.parse_edit_prompt("Make it 150 mm wide but keep the same thickness.")

    assert result["ok"] is True
    assert result["edit_request"]["edits"][0]["parameter"] == "width"
    assert "thickness" in result["edit_request"]["preserve"]


def test_parse_apply_edit_prompt_accepts_width_edit(tmp_path: Path) -> None:
    _require_cadquery()

    result = tools.parse_apply_edit_prompt(
        "bracket",
        "Make it 150 mm wide but keep the same thickness.",
        output_root=str(tmp_path),
    )

    assert result["ok"] is True
    assert result["accepted"] is True
    assert result["validation_valid"] is True
    assert result["edit_report"]["updated_parameters"]["back_plate_width_mm"] == 150.0
    assert (tmp_path / "bracket_edited.step").stat().st_size > 0


def test_parse_apply_edit_prompt_rejects_vague_edit(tmp_path: Path) -> None:
    result = tools.parse_apply_edit_prompt("bracket", "Make it better.", output_root=str(tmp_path))

    assert result["ok"] is False
    assert result["accepted"] is False
    assert result["cad_exported"] is False
    assert "measurable" in result["message"]
    assert not (tmp_path / "bracket_edited.step").exists()


def test_parse_apply_edit_prompt_rejects_three_hole_edit(tmp_path: Path) -> None:
    result = tools.parse_apply_edit_prompt("bracket", "Change it to three mounting holes.", output_root=str(tmp_path))

    assert result["ok"] is False
    assert result["accepted"] is False
    assert result["cad_exported"] is False
    assert "two or four holes" in result["message"]
    assert not (tmp_path / "bracket_edited.step").exists()


def test_rejected_edit_does_not_overwrite_existing_cad(tmp_path: Path) -> None:
    _require_cadquery()

    accepted = tools.parse_apply_edit_prompt("bracket", "Change it to four mounting holes.", output_root=str(tmp_path))
    latest_step = tmp_path / "bracket_edited.step"
    latest_stl = tmp_path / "bracket_edited.stl"
    step_before = latest_step.read_bytes()
    stl_before = latest_stl.read_bytes()

    rejected = tools.parse_apply_edit_prompt("bracket", "Change it to three mounting holes.", output_root=str(tmp_path))

    assert accepted["accepted"] is True
    assert rejected["accepted"] is False
    assert latest_step.read_bytes() == step_before
    assert latest_stl.read_bytes() == stl_before
    rejected_run_dir = tmp_path / "edit_parse_runs" / rejected["run_id"]
    assert not (rejected_run_dir / "bracket_edited.step").exists()


def test_build_example_bracket_exports_cad(tmp_path: Path) -> None:
    _require_cadquery()

    result = tools.build_example_bracket("bracket", output_root=str(tmp_path))

    assert result["ok"] is True
    assert Path(result["step_path"]).stat().st_size > 0
    assert Path(result["stl_path"]).stat().st_size > 0


def test_validate_example_bracket_writes_report(tmp_path: Path) -> None:
    _require_cadquery()

    result = tools.validate_example_bracket("bracket", output_root=str(tmp_path))

    assert result["ok"] is True
    assert result["valid"] is True
    assert result["failed_checks"] == 0
    assert Path(result["report_path"]).exists()


def test_list_recent_runs_returns_recent_parsed_runs(tmp_path: Path) -> None:
    runs_dir = tmp_path / "parsed_runs" / "20260708_120000_example"
    runs_dir.mkdir(parents=True)
    (runs_dir / "run_metadata.json").write_text(
        json.dumps({"run_id": runs_dir.name, "created_at": "2026-07-08T12:00:00+00:00", "command_type": "parse-build"}),
        encoding="utf-8",
    )

    result = tools.list_recent_runs("parsed_runs", limit=5, output_root=str(tmp_path))

    assert result["ok"] is True
    assert result["runs"][0]["run_id"] == runs_dir.name
    assert result["runs"][0]["command_type"] == "parse-build"


def test_get_run_metadata_returns_metadata(tmp_path: Path) -> None:
    runs_dir = tmp_path / "edit_parse_runs" / "20260708_120000_edit"
    runs_dir.mkdir(parents=True)
    metadata = {"run_id": runs_dir.name, "created_at": "2026-07-08T12:00:00+00:00", "command_type": "edit-parse"}
    (runs_dir / "run_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    result = tools.get_run_metadata("edit_parse_runs", runs_dir.name, output_root=str(tmp_path))

    assert result["ok"] is True
    assert result["metadata"] == metadata


def test_invalid_run_kind_is_rejected(tmp_path: Path) -> None:
    listed = tools.list_recent_runs("unknown_runs", output_root=str(tmp_path))
    metadata = tools.get_run_metadata("unknown_runs", "abc", output_root=str(tmp_path))

    assert listed["ok"] is False
    assert listed["error_type"] == "ValueError"
    assert metadata["ok"] is False
    assert metadata["error_type"] == "ValueError"


def test_mcp_server_can_be_created_when_mcp_package_is_available() -> None:
    pytest.importorskip("mcp")

    from mcp_server.server import create_server

    server = create_server()

    assert server is not None
