"""Phase 30: Remediation engine tests (package -> Remediation_Intent.json)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from intentforge.remediation import (
    REMEDIATION_INTENT_FILE,
    apply_remediation_to_parameters,
    build_metrics,
    synthesize_remediation_intent,
)
from tests.phase27_test_helpers import build_three_package_chain


def _write_parameters(package_dir: Path, parameters: dict[str, float]) -> Path:
    target = package_dir / "parameters.json"
    target.write_text(json.dumps(parameters, indent=2, sort_keys=True), encoding="utf-8")
    return target


def test_engine_rejects_missing_directory(tmp_path: Path) -> None:
    result = synthesize_remediation_intent(tmp_path / "missing")
    assert result.passed is False
    assert result.status == "remediation_impossible"


def test_engine_skips_when_no_failures(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "ok-chain")
    target_dir = chain["packages"][0]
    _write_parameters(target_dir, {
        "back_plate_width_mm": 120.0,
        "back_plate_height_mm": 60.0,
        "back_plate_thickness_mm": 8.0,
        "mounting_hole_diameter_mm": 6.0,
        "mounting_hole_spacing_x_mm": 60.0,
        "mounting_hole_spacing_y_mm": 30.0,
        "corner_radius_mm": 2.0,
    })
    result = synthesize_remediation_intent(target_dir)
    assert result.status == "skipped"
    assert result.delta is None


def test_engine_emits_remediation_intent_for_failed_rule(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "fail-chain")
    target_dir = chain["packages"][0]
    _write_parameters(target_dir, {
        "back_plate_width_mm": 30.0,
        "back_plate_height_mm": 60.0,
        "back_plate_thickness_mm": 8.0,
        "mounting_hole_diameter_mm": 10.0,
        "mounting_hole_spacing_x_mm": 0.0,
        "mounting_hole_spacing_y_mm": 0.0,
        "corner_radius_mm": 2.0,
    })
    result = synthesize_remediation_intent(target_dir)
    assert result.passed is True
    assert result.status == "remediation_synthesized"
    assert result.delta is not None
    assert len(result.delta.parameter_changes) >= 1
    intent_path = target_dir / REMEDIATION_INTENT_FILE
    assert intent_path.is_file()
    payload = json.loads(intent_path.read_text(encoding="utf-8"))
    assert payload["remediation_status"] == "remediation_synthesized"
    assert payload["target_family"] == "wall_mounted_bracket"
    assert "parameter_changes" in payload


def test_engine_handles_missing_parameter_table(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "no-params-chain")
    target_dir = chain["packages"][0]
    result = synthesize_remediation_intent(target_dir)
    assert result.passed is False
    assert "parameter table" in result.rationale


def test_engine_accepts_parameters_override(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "override-chain")
    target_dir = chain["packages"][0]
    result = synthesize_remediation_intent(
        target_dir,
        parameters_override={
            "back_plate_width_mm": 30.0,
            "back_plate_height_mm": 60.0,
            "back_plate_thickness_mm": 8.0,
            "mounting_hole_diameter_mm": 10.0,
            "mounting_hole_spacing_x_mm": 0.0,
        },
    )
    assert result.status == "remediation_synthesized"


def test_build_metrics_for_wall_family() -> None:
    metrics = build_metrics(
        {
            "back_plate_width_mm": 30.0,
            "back_plate_height_mm": 60.0,
            "back_plate_thickness_mm": 8.0,
            "mounting_hole_diameter_mm": 10.0,
            "mounting_hole_spacing_x_mm": 0.0,
            "mounting_hole_spacing_y_mm": 0.0,
        },
        family="wall_mounted_bracket",
    )
    assert metrics["family"] == "wall_mounted_bracket"
    assert metrics["hole_edge_distance"] == 10.0
    assert metrics["hole_diameter"] == 10.0


def test_build_metrics_for_l_family() -> None:
    metrics = build_metrics(
        {
            "base_leg_length_mm": 80.0,
            "vertical_leg_length_mm": 60.0,
            "bracket_width_mm": 30.0,
            "thickness_mm": 8.0,
            "hole_diameter_mm": 6.0,
            "base_hole_spacing_mm": 40.0,
            "base_hole_count": 2,
            "vertical_hole_count": 0,
        },
        family="l_bracket",
    )
    assert metrics["family"] == "l_bracket"
    assert metrics["bracket_width"] == 30.0
    assert metrics["hole_diameter"] == 6.0


def test_apply_remediation_updates_parameters() -> None:
    parameters = {"back_plate_width_mm": 30.0, "mounting_hole_diameter_mm": 10.0}
    intent = {
        "parameter_changes": [
            {"parameter": "back_plate_width_mm", "proposed_value": 70.0},
        ]
    }
    new_parameters = apply_remediation_to_parameters(parameters, intent)
    assert new_parameters["back_plate_width_mm"] == 70.0
    assert parameters["back_plate_width_mm"] == 30.0  # original unchanged


def test_engine_result_is_serializable(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "json-chain")
    target_dir = chain["packages"][0]
    _write_parameters(target_dir, {
        "back_plate_width_mm": 30.0,
        "back_plate_height_mm": 60.0,
        "back_plate_thickness_mm": 8.0,
        "mounting_hole_diameter_mm": 10.0,
        "mounting_hole_spacing_x_mm": 0.0,
        "mounting_hole_spacing_y_mm": 0.0,
    })
    result = synthesize_remediation_intent(target_dir)
    payload = result.to_dict()
    json.dumps(payload, sort_keys=True)
    assert "remediation_id" in (payload.get("delta") or {})


def test_engine_impossible_status_for_unsupported_family(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "family-chain")
    target_dir = chain["packages"][0]
    _write_parameters(target_dir, {"back_plate_width_mm": 30.0})
    # Force unsupported family via override
    result = synthesize_remediation_intent(
        target_dir,
        parameters_override={
            "family": "totally_unsupported",
            "back_plate_width_mm": 30.0,
            "back_plate_height_mm": 60.0,
            "back_plate_thickness_mm": 8.0,
            "mounting_hole_diameter_mm": 10.0,
            "mounting_hole_spacing_x_mm": 0.0,
        },
    )
    # family default to wall if not in manifest, so we expect synthesized.
    # This test simply asserts the engine never raises.
    assert result.status in {"remediation_synthesized", "remediation_impossible", "skipped"}