"""Phase 35 manufacturing metadata, routing-slip CAS, and redaction tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from intentforge.assemblies import build_assembly_intent_workflow, validate_assembly_audit_package
from intentforge.manufacturing.cas import validate_component_manufacturing_envelope
from intentforge.manufacturing.schema import (
    GeometricTolerance,
    ManufacturingRequirements,
    MaterialSpecification,
    SurfaceRoughnessRequirement,
)
from intentforge.redaction import default_redaction_config
from intentforge.redaction.engine import prune_document
from intentforge.topology.registry import get_topology_registry
from intentforge.workflows import parse_build_intent_workflow


def _assembly_payload() -> dict:
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
                "nominal_diameter": 8.0,
                "thread_pitch": 1.25,
                "shank_length": 10.0,
                "thread_length": 20.0,
                "head_type": "hexagonal",
            },
        },
    }


def test_manufacturing_schema_is_typed_and_conservative() -> None:
    requirements = ManufacturingRequirements(
        material_specification=MaterialSpecification(
            material_grade="SS316L", hardness="HRB_95_Max", surface_treatment="Passivated"
        ),
        surface_roughness=[
            SurfaceRoughnessRequirement(controlled_feature="mating_face", requirement="Ra_3.2")
        ],
        geometric_tolerances=[
            GeometricTolerance(
                controlled_feature="mating_face",
                tolerance_type="flatness",
                maximum_allowable_deviation_mm=0.1,
            )
        ],
    )
    assert requirements.material_specification.material_grade == "SS316L"
    with pytest.raises(ValidationError, match="concentricity requires"):
        GeometricTolerance(
            controlled_feature="bore_hole",
            tolerance_type="concentricity",
            maximum_allowable_deviation_mm=0.05,
        )


def test_golden_topology_manufacturing_requirements() -> None:
    registry = get_topology_registry()
    flange = registry.get("industrial_flange").manufacturing_requirements
    gear = registry.get("spur_gear").manufacturing_requirements
    assert flange is not None and flange.material_specification.model_dump() == {
        "material_grade": "SS316L",
        "hardness": "HRB_95_Max",
        "surface_treatment": "Passivated",
    }
    assert flange.surface_roughness[0].requirement == "Ra_3.2"
    assert flange.geometric_tolerances[0].maximum_allowable_deviation_mm == 0.1
    assert gear is not None and gear.material_specification.material_grade == "AISI_4140"
    assert gear.surface_roughness[0].requirement == "Ra_1.6"
    assert gear.geometric_tolerances[0].reference_feature == "pitch_circle"
    assert gear.geometric_tolerances[0].maximum_allowable_deviation_mm == 0.05
    assert registry.get("standard_bolt").manufacturing_requirements is None


@pytest.mark.parametrize("family", ["industrial_flange", "spur_gear"])
def test_component_export_writes_order_and_merkle_cas(tmp_path: Path, family: str) -> None:
    pytest.importorskip("cadquery")
    result = parse_build_intent_workflow({"family": family, "parameters": {}}, tmp_path / family)
    assert result["ok"] and result["validation_valid"] and result["cad_exported"]
    order_path = Path(result["latest_outputs"]["manufacturing_order"])
    envelope_path = Path(result["latest_outputs"]["manufacturing_cas_envelope"])
    assert order_path.name == "manufacturing_order.json" and order_path.is_file()
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    assert any(item["role"] == "manufacturing_order" for item in envelope["leaves"])
    assert envelope["manufacturing_order_content_address"] == result["manufacturing_order"]["content_address"]
    validation = validate_component_manufacturing_envelope(
        envelope_path, manifest=get_topology_registry().get(family)
    )
    assert validation["passed"] and validation["merkle_root"] == envelope["merkle_root"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda order: order["items"][0]["requirements"]["material_specification"].update(
            material_grade="SS304"
        ),
        lambda order: order["items"][0]["requirements"]["geometric_tolerances"][0].update(
            maximum_allowable_deviation_mm=1.0
        ),
    ],
)
def test_component_manufacturing_tamper_breaks_cas(tmp_path: Path, mutation) -> None:
    pytest.importorskip("cadquery")
    result = parse_build_intent_workflow(
        {"family": "industrial_flange", "parameters": {}}, tmp_path
    )
    order_path = Path(result["latest_outputs"]["manufacturing_order"])
    order = json.loads(order_path.read_text(encoding="utf-8"))
    mutation(order)
    order_path.write_text(json.dumps(order, sort_keys=True), encoding="utf-8")
    validation = validate_component_manufacturing_envelope(
        result["latest_outputs"]["manufacturing_cas_envelope"],
        manifest=get_topology_registry().get("industrial_flange"),
    )
    assert not validation["passed"]
    assert any("manufacturing" in error for error in validation["errors"])


def test_assembly_order_is_direct_parent_leaf_and_child_bound(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = build_assembly_intent_workflow(_assembly_payload(), tmp_path)
    assert result["ok"] and result["cad_exported"]
    order = json.loads(Path(result["manufacturing_order_path"]).read_text(encoding="utf-8"))
    assert order["order_scope"] == "assembly"
    assert [(item["item_id"], item["quantity"]) for item in order["items"]] == [
        ("flange", 1), ("bolt", 4)
    ]
    package_root = Path(result["audit_package"]["package_path"])
    envelope = json.loads((package_root / "assembly_cas_envelope.json").read_text(encoding="utf-8"))
    assert envelope["manufacturing_order_leaf_address"] in envelope["assembly_merkle_leaves"]
    children = json.loads((package_root / "child_components.json").read_text(encoding="utf-8"))
    assert all(item["manufacturing_order_content_address"].startswith("sha256:") for item in children)
    assert validate_assembly_audit_package(package_root)["passed"]


def test_assembly_manufacturing_order_tamper_breaks_parent_cas(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = build_assembly_intent_workflow(_assembly_payload(), tmp_path)
    package_root = Path(result["audit_package"]["package_path"])
    order_path = package_root / "manufacturing_order.json"
    order = json.loads(order_path.read_text(encoding="utf-8"))
    order["items"][0]["requirements"]["material_specification"]["material_grade"] = "SS304"
    order_path.write_text(json.dumps(order, sort_keys=True), encoding="utf-8")
    validation = validate_assembly_audit_package(package_root)
    assert not validation["passed"]
    assert any("manufacturing" in error or "checksum" in error for error in validation["errors"])


def test_default_redaction_masks_hardness_and_gdt_values() -> None:
    manifest = get_topology_registry().get("spur_gear")
    document = {
        "manufacturing_order": {
            "requirements": manifest.manufacturing_requirements.model_dump(mode="json")
        }
    }
    result = prune_document(document, default_redaction_config())
    encoded = json.dumps(result.redacted_document, sort_keys=True)
    assert "HRC_30_35" not in encoded
    assert "Ra_1.6" not in encoded
    assert "0.05" not in encoded
    assert "[REDACTED_MATERIAL_VALUE]" in encoded
    assert "[REDACTED_NUMERIC_VALUE]" in encoded
