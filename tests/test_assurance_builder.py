from pathlib import Path

import pytest

from intentforge.assurance import build_assurance_case, build_assurance_from_prompt, validate_assurance_case
from intentforge.workflows import parse_build_workflow


def test_wall_static_assurance_build() -> None:
    case = build_assurance_from_prompt(profile="static", family="wall_mounted_bracket")
    assert case.cad_family == "wall_mounted_bracket"
    assert validate_assurance_case(case).passed


def test_l_bracket_standard_dry_run(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    case = build_assurance_from_prompt(profile="standard", family="l_bracket", dry_run=True, output_root=tmp_path)
    assert any(item.validation_type == "geometry_validation" for item in case.validation_observations)
    assert not any(item.claim_type == "geometry_generated" for item in case.claims)


def test_full_build_identity_ignores_run_paths_and_export_metadata(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    output_root = tmp_path / "output" / "determinism"
    first = build_assurance_from_prompt(profile="full", output_root=output_root, request_id="first")
    second = build_assurance_from_prompt(profile="full", output_root=output_root, request_id="second")
    assert first.assurance_case_id == second.assurance_case_id
    assert all("parsed_runs" not in item.path for item in first.artifact_records)


def test_intentional_rejection_is_scoped_assurance(tmp_path: Path) -> None:
    result = parse_build_workflow("Make a gear with 24 teeth.", tmp_path, dry_run=True)
    result["object_type"] = "wall_mounted_bracket"
    case = build_assurance_case(result, profile="static", input_request="Make a gear with 24 teeth.")
    assert case.overall_assurance_status == "assurance_complete_with_limitations"
    assert any(item.claim_type == "unsupported_behavior_rejected" for item in case.claims)
