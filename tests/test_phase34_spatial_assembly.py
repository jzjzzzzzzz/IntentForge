"""Phase 34 assembly registry, nested evaluation, geometry, and CAS tests."""

from __future__ import annotations

from importlib.resources import files
import json
from pathlib import Path

import pytest

from intentforge.assemblies import (
    AssemblyManifest,
    build_assembly_intent_workflow,
    get_assembly_registry,
    validate_assembly_audit_package,
)
from intentforge.topology.registry import RegistryManager


def _payload(*, diameter: float = 8.0, shank: float = 10.0, thread: float = 20.0) -> dict:
    return {
        "assembly_family": "flange_bolted_joint",
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


def test_assembly_manifest_schema_and_dynamic_registry() -> None:
    topology_registry = RegistryManager.load()
    manifest = topology_registry.get_assembly("flange_bolted_joint")
    assert isinstance(manifest, AssemblyManifest)
    assert topology_registry.assembly_count() == 1
    assert get_assembly_registry().get("bolted flange").assembly_family == "flange_bolted_joint"
    assert [(item.component_id, item.topology_family) for item in manifest.components] == [
        ("flange", "industrial_flange"),
        ("bolt", "standard_bolt"),
    ]
    assert topology_registry.assembly_snapshot() == RegistryManager.load().assembly_snapshot()


def test_assembly_manifest_uses_closed_algebraic_bindings() -> None:
    manifest = get_assembly_registry().get("flange_bolted_joint")
    clearance = next(item for item in manifest.spatial_constraints if item.constraint_id == "bolt_hole_coaxial_clearance")
    assert clearance.operator == "lt"
    assert clearance.right_expression == "flange_bolt_hole_diameter - flange_bore_clearance"
    length = next(item for item in manifest.spatial_constraints if item.constraint_id == "bolt_body_length_through_flange")
    assert length.left_expression == "bolt_shank_length + bolt_thread_length"
    assert length.operator == "ge"


def test_nested_evaluation_passes_before_spatial_constraints(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = build_assembly_intent_workflow(_payload(), tmp_path, dry_run=True)
    report = result["evaluation"]
    assert result["ok"] and not result["cad_exported"]
    assert result["component_quantities"] == {"flange": 1, "bolt": 4}
    assert report["nested_validation_passed"] is True
    assert len(report["child_observations"]) == 5
    assert [item["status"] for item in report["constraint_observations"]] == ["pass", "pass"]


@pytest.mark.parametrize(
    "payload,constraint_id",
    [
        (_payload(diameter=13.5), "bolt_hole_coaxial_clearance"),
        (_payload(shank=0.0, thread=2.0), "bolt_body_length_through_flange"),
    ],
)
def test_blocking_spatial_constraint_prevents_assembly_export(
    tmp_path: Path, payload: dict, constraint_id: str,
) -> None:
    pytest.importorskip("cadquery")
    result = build_assembly_intent_workflow(payload, tmp_path)
    failures = [item for item in result["evaluation"]["constraint_observations"] if item["status"] == "fail"]
    assert result["ok"] is False and result["cad_exported"] is False
    assert [item["constraint_id"] for item in failures] == [constraint_id]
    assert not list(tmp_path.rglob("*.step"))


def test_flange_bolted_joint_e2e_step_and_nested_merkle(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = build_assembly_intent_workflow(_payload(), tmp_path)
    assert result["ok"] and result["cad_exported"]
    assert Path(result["assembly_step_path"]).is_file()
    assert Path(result["assembly_step_path"]).stat().st_size > 0
    assert result["nested_merkle_root"].startswith("sha256:")
    package = result["audit_package"]
    assert package["child_component_count"] == 5
    assert package["validation"]["passed"]
    child_records = json.loads(
        (Path(package["package_path"]) / "child_components.json").read_text(encoding="utf-8")
    )
    assert all(item["topology_manifest_content_address"].startswith("sha256:") for item in child_records)
    assert len({item["content_address"] for item in child_records}) == 5


def test_child_topology_tamper_breaks_parent_assembly_package(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = build_assembly_intent_workflow(_payload(), tmp_path / "run")
    package_root = Path(result["audit_package"]["package_path"])
    child_path = package_root / "children" / "bolt_001.step"
    child_path.write_bytes(child_path.read_bytes() + b"tampered")
    validation = validate_assembly_audit_package(package_root)
    assert validation["passed"] is False
    assert any("child artifact hash mismatch" in item for item in validation["errors"])


def test_assembly_manifest_is_packaged() -> None:
    manifest = files("intentforge").joinpath(
        "knowledge", "assemblies", "flange_bolted_joint", "manifest.yaml"
    )
    assert manifest.is_file()
