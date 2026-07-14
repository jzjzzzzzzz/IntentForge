"""Manifest-authorized parent/child assembly remediation tests."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from intentforge.assemblies import build_assembly_intent_workflow
from intentforge.assemblies.registry import get_assembly_registry


def _payload(*, diameter: float = 8.0, shank: float = 10.0, thread: float = 20.0) -> dict:
    return {
        "assembly_family": "flange_bolted_joint",
        "auto_remediate": True,
        "components": {
            "flange": {
                "flange_outer_diameter": 150.0,
                "bolt_circle_diameter": 110.0,
                "bolt_hole_diameter": 14.0,
                "hole_count": 4,
                "flange_thickness": 18.0,
                "bore_diameter": 60.0,
                "bore_clearance": 0.5,
            },
            "bolt": {
                "nominal_diameter": diameter,
                "thread_pitch": 1.25,
                "shank_length": shank,
                "thread_length": thread,
                "head_type": "hexagonal",
            },
        },
    }


def _parameter_value(result: dict, component: str, name: str, *, requested: bool = False):
    key = "requested_component_parameters" if requested else "component_parameters"
    parameters = result[key][component]["parameters"]
    return next(item["value"] for item in parameters if item["name"] == name)


def test_manifest_declares_closed_cross_component_remediation_targets() -> None:
    manifest = get_assembly_registry().get("flange_bolted_joint")
    strategies = {
        item.constraint_id: item.remediation
        for item in manifest.spatial_constraints
    }
    clearance = strategies["bolt_hole_coaxial_clearance"]
    length = strategies["bolt_body_length_through_flange"]
    assert clearance is not None
    assert (clearance.target_variable, clearance.direction, clearance.boundary_margin) == (
        "flange_bolt_hole_diameter", "increase", 0.1
    )
    assert length is not None
    assert (length.target_variable, length.direction, length.boundary_margin) == (
        "bolt_thread_length", "increase", 0.5
    )


def test_clearance_conflict_remediates_parent_flange_and_revalidates(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = build_assembly_intent_workflow(
        _payload(diameter=13.5), tmp_path, dry_run=True
    )
    assert result["ok"] and result["remediation_applied"]
    assert _parameter_value(result, "flange", "bolt_hole_diameter", requested=True) == 14.0
    assert _parameter_value(result, "flange", "bolt_hole_diameter") == pytest.approx(14.1)
    assert result["remediation_actions"][0]["component_id"] == "flange"
    assert result["remediation_actions"][0]["parameter_name"] == "bolt_hole_diameter"
    assert all(item["validation_passed"] for item in result["evaluation"]["child_observations"])
    assert [item["status"] for item in result["evaluation"]["constraint_observations"]] == [
        "pass", "pass"
    ]


def test_length_conflict_remediates_child_bolt_and_revalidates(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = build_assembly_intent_workflow(
        _payload(shank=0.0, thread=2.0), tmp_path, dry_run=True
    )
    assert result["ok"] and result["remediation_applied"]
    assert _parameter_value(result, "bolt", "thread_length", requested=True) == 2.0
    assert _parameter_value(result, "bolt", "thread_length") == pytest.approx(18.5)
    assert result["remediation_actions"][0]["component_id"] == "bolt"
    assert result["remediation_actions"][0]["parameter_name"] == "thread_length"
    length = next(
        item for item in result["evaluation"]["constraint_observations"]
        if item["constraint_id"] == "bolt_body_length_through_flange"
    )
    assert length["status"] == "pass" and length["left_value"] == pytest.approx(18.5)


def test_remediation_is_opt_in_to_preserve_blocking_contract(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    payload = _payload(diameter=13.5)
    payload.pop("auto_remediate")
    result = build_assembly_intent_workflow(payload, tmp_path, dry_run=True)
    assert not result["ok"]
    assert not result["remediation_applied"]
    assert result["remediation_actions"] == []
    assert _parameter_value(result, "flange", "bolt_hole_diameter") == 14.0


def test_remediated_parameters_are_bound_into_child_merkle_package(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = build_assembly_intent_workflow(
        _payload(diameter=13.5, shank=0.0, thread=2.0), tmp_path
    )
    assert result["ok"] and result["cad_exported"]
    assert len(result["remediation_actions"]) == 2
    package_root = Path(result["audit_package"]["package_path"])
    records = json.loads((package_root / "child_components.json").read_text(encoding="utf-8"))
    flange = next(item for item in records if item["component_id"] == "flange")
    bolt = next(item for item in records if item["component_id"] == "bolt")
    flange_parameters = {item["name"]: item["value"] for item in flange["parameter_table"]["parameters"]}
    bolt_parameters = {item["name"]: item["value"] for item in bolt["parameter_table"]["parameters"]}
    assert flange_parameters["bolt_hole_diameter"] == pytest.approx(14.1)
    assert bolt_parameters["thread_length"] == pytest.approx(18.5)
    assert result["audit_package"]["validation"]["passed"]


def test_registered_json_cli_dispatches_to_assembly_workflow(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    intent_path = tmp_path / "assembly_intent.json"
    intent_path.write_text(json.dumps(_payload(diameter=13.5)), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "intentforge.cli",
            "topology",
            "build-json",
            str(intent_path),
            "--output-root",
            str(tmp_path / "output"),
            "--dry-run",
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["assembly_family"] == "flange_bolted_joint"
    assert result["ok"] and result["remediation_applied"] and not result["cad_exported"]
