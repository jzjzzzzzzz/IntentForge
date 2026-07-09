from pathlib import Path

import pytest

from intentforge.contracts import ArtifactRef, ToolError, ToolResponse
from intentforge.generator.cadquery_generator import CadQueryUnavailableError
from intentforge import workflows
from intentforge.workflows import edit_parse_apply_workflow, parse_build_workflow
from mcp_server import tools


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def test_contract_models_accept_standard_success_shape() -> None:
    response = ToolResponse(
        ok=True,
        request_id="req_test",
        run_id="run_test",
        object_type="wall_mounted_bracket",
        operation="parse_build",
        artifacts=[
            ArtifactRef(
                kind="step",
                path="output/parsed_bracket.step",
                persistent=False,
                object_type="wall_mounted_bracket",
            )
        ],
        warnings=[],
        metadata={},
    )

    assert response.ok is True
    assert response.request_id == "req_test"
    assert response.operation == "parse_build"
    assert response.artifacts[0].kind == "step"


def test_contract_models_accept_standard_error_shape() -> None:
    response = ToolResponse(
        ok=False,
        request_id="req_test",
        operation="parse_build",
        artifacts=[],
        error=ToolError(
            error_type="UnsupportedObjectError",
            message="Unsupported object type.",
            recoverable=True,
            suggested_action="Use a supported model family.",
        ),
        cad_exported=False,
        warnings=[],
    )

    assert response.ok is False
    assert response.error is not None
    assert response.error.message == "Unsupported object type."
    assert response.cad_exported is False


def test_success_response_includes_request_id_operation_and_artifacts(tmp_path: Path) -> None:
    _require_cadquery()

    result = parse_build_workflow(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes.",
        tmp_path,
        request_id="req_contract_success",
    )

    assert result["ok"] is True
    assert result["request_id"] == "req_contract_success"
    assert result["operation"] == "parse_build"
    assert result["object_type"] == "wall_mounted_bracket"
    assert result["validation"]["valid"] is True
    assert any(artifact["kind"] == "step" and artifact["path"] for artifact in result["artifacts"])


def test_error_response_includes_error_message() -> None:
    result = workflows.parse_prompt_workflow("Make a gear with 24 teeth.", request_id="req_contract_error")

    assert result["ok"] is False
    assert result["request_id"] == "req_contract_error"
    assert result["operation"] == "parse"
    assert result["error"]["error_type"] == "UnsupportedObjectError"
    assert "Unsupported object type" in result["error"]["message"]
    assert result["artifacts"] == []


def test_artifact_refs_have_kind_and_path(tmp_path: Path) -> None:
    _require_cadquery()

    result = parse_build_workflow(
        "Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, and 6 mm thick.",
        tmp_path,
    )

    assert result["artifacts"]
    assert all(artifact["kind"] for artifact in result["artifacts"])
    assert all(artifact["path"] for artifact in result["artifacts"])


def test_dry_run_parse_build_does_not_export_step_or_stl(tmp_path: Path) -> None:
    _require_cadquery()

    result = parse_build_workflow(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes.",
        tmp_path,
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["cad_exported"] is False
    assert "step" not in result["latest_outputs"]
    assert "stl" not in result["latest_outputs"]
    assert not (tmp_path / "parsed_bracket.step").exists()
    assert not (tmp_path / "parsed_bracket.stl").exists()
    planned_step_refs = [
        artifact
        for artifact in result["artifacts"]
        if artifact["kind"] == "step" and artifact["metadata"].get("planned")
    ]
    assert planned_step_refs


def test_rejected_edit_returns_contract_error_and_no_cad(tmp_path: Path) -> None:
    result = edit_parse_apply_workflow(
        "bracket",
        "Make it better.",
        tmp_path,
        request_id="req_rejected_edit",
    )

    assert result["ok"] is False
    assert result["accepted"] is False
    assert result["cad_exported"] is False
    assert result["request_id"] == "req_rejected_edit"
    assert result["operation"] == "edit_parse_apply"
    assert result["error"]["message"]
    assert result["artifacts"] == []
    assert not (tmp_path / "bracket_edited.step").exists()


def test_mcp_parse_build_output_follows_contract(tmp_path: Path) -> None:
    _require_cadquery()

    result = tools.parse_build_cad_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes.",
        output_root=str(tmp_path),
        request_id="req_mcp_parse_build",
    )

    assert result["ok"] is True
    assert result["request_id"] == "req_mcp_parse_build"
    assert result["operation"] == "parse_build"
    assert result["validation"]["valid"] is True
    assert result["artifacts"]


def test_mcp_rejected_edit_output_follows_contract(tmp_path: Path) -> None:
    result = tools.parse_apply_edit_prompt(
        "bracket",
        "Make it better.",
        output_root=str(tmp_path),
        request_id="req_mcp_rejected_edit",
    )

    assert result["ok"] is False
    assert result["request_id"] == "req_mcp_rejected_edit"
    assert result["operation"] == "edit_parse_apply"
    assert result["accepted"] is False
    assert result["cad_exported"] is False
    assert result["error"]["message"]
    assert result["artifacts"] == []


def test_no_cadquery_error_is_structured_as_backend_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _raise_backend_unavailable(*args, **kwargs):
        raise CadQueryUnavailableError("CadQuery is required for CAD generation.")

    monkeypatch.setattr(workflows, "_build_model", _raise_backend_unavailable)

    result = parse_build_workflow(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes.",
        tmp_path,
        request_id="req_no_backend",
    )

    assert result["ok"] is False
    assert result["request_id"] == "req_no_backend"
    assert result["error"]["error_type"] == "CadBackendUnavailableError"
    assert result["cad_exported"] is False
