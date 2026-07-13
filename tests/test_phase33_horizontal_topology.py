"""Phase 33 gear and bolt registry, algebra, CAD, and audit qualification tests."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import pytest

from intentforge.assurance import build_assurance_case, build_audit_package, validate_audit_package
from intentforge.dossier import build_dossier, verify_release_dossier, write_dossier
from intentforge.parser.registered_parser import build_registered_intent_json_schema, parse_registered_intent
from intentforge.remediation.algebra import metric_to_parameter_transform
from intentforge.review import evaluate_assurance_case, get_review_policy
from intentforge.topology.expressions import evaluate_numeric_expression, solve_parameter_for_metric
from intentforge.topology.registry import RegistryManager, get_topology_registry
from intentforge.workflows import parse_build_intent_workflow


GEAR = {"module": 2.0, "teeth_count": 20, "pressure_angle": 20.0, "face_width": 16.0, "bore_diameter": 12.0}
BOLT = {"nominal_diameter": 8.0, "thread_pitch": 1.25, "shank_length": 20.0, "thread_length": 25.0, "head_type": "hexagonal"}


def test_registry_loads_three_industrial_families_together() -> None:
    registry = RegistryManager.load()
    assert [item.topology_family for item in registry.all(active_only=True)] == [
        "industrial_flange", "l_bracket", "spur_gear", "standard_bolt", "wall_mounted_bracket",
    ]
    assert registry.get("spur gear").topology_family == "spur_gear"
    assert registry.get("metric bolt").topology_family == "standard_bolt"


def test_spur_gear_manifest_formulas_and_closed_solver() -> None:
    manifest = get_topology_registry().get("spur_gear")
    assert len(set(manifest.capability_evidence_binding.evidence_catalog_ids)) == 65
    assert evaluate_numeric_expression(manifest.metric_mapping("pitch_circle_diameter").expression, GEAR) == 40.0
    assert evaluate_numeric_expression(manifest.metric_mapping("root_circle_diameter").expression, GEAR) == 35.0
    margin_mapping = manifest.metric_mapping("bore_material_margin")
    assert evaluate_numeric_expression(margin_mapping.expression, GEAR) == 11.5
    solved = solve_parameter_for_metric(
        margin_mapping.expression,
        target_metric_value=4.0,
        parameter_name="bore_diameter",
        parameters={**GEAR, "bore_diameter": 30.0},
        safe_bounds=manifest.parameter("bore_diameter").safe_bounds,
    )
    assert solved == pytest.approx(27.0)
    assert metric_to_parameter_transform(
        family="spur_gear", metric="hole_edge_distance", target_metric_value=4.0,
        parameters={**GEAR, "bore_diameter": 30.0},
    ) == pytest.approx(27.0)


def test_standard_bolt_manifest_stress_area_and_enum_schema() -> None:
    manifest = get_topology_registry().get("standard_bolt")
    assert len(set(manifest.capability_evidence_binding.evidence_catalog_ids)) == 65
    assert evaluate_numeric_expression(manifest.metric_mapping("total_length").expression, BOLT) == 45.0
    assert evaluate_numeric_expression(manifest.metric_mapping("tensile_stress_area").expression, BOLT) == pytest.approx(36.608, rel=1e-3)
    stress_mapping = manifest.metric_mapping("tensile_stress_area")
    solved = metric_to_parameter_transform(
        family="standard_bolt", metric="tensile_stress_area", target_metric_value=50.0, parameters=BOLT,
    )
    assert evaluate_numeric_expression(stress_mapping.expression, {**BOLT, "nominal_diameter": solved}) == pytest.approx(50.0)
    schema = build_registered_intent_json_schema("standard_bolt")
    assert schema["properties"]["parameters"]["properties"]["head_type"]["enum"] == ["hexagonal", "socket_cap"]
    with pytest.raises(ValueError, match="must be one of"):
        parse_registered_intent({"family": "standard_bolt", "parameters": {**BOLT, "head_type": "wing"}})


@pytest.mark.parametrize(("family", "parameters"), [("spur_gear", GEAR), ("standard_bolt", BOLT)])
def test_new_family_build_assurance_cas_and_dossier(
    tmp_path: Path, family: str, parameters: dict[str, object],
) -> None:
    pytest.importorskip("cadquery")
    result = parse_build_intent_workflow(
        {"family": family, "parameters": parameters}, tmp_path / family, request_id=f"phase33_{family}",
    )
    assert result["ok"] and result["cad_exported"] and result["validation"]["valid"]
    step_artifacts = [item for item in result["artifacts"] if item.get("kind") == "step"]
    assert step_artifacts and Path(step_artifacts[0]["path"]).is_file()
    case = build_assurance_case(result, profile="standard", input_request=family)
    policy = get_review_policy("intentforge_standard_design_review_v1")
    decision = evaluate_assurance_case(policy, case, result)
    package_dir = tmp_path / f"{family}_package"
    package = build_audit_package(case, package_dir, review_policy=policy, review_decision=decision)
    assert validate_audit_package(package_dir)["passed"]
    assert package["package_id"].startswith("sha256:")
    dossier_dir = tmp_path / f"{family}_dossier"
    dossier = build_dossier([package_dir])
    write_dossier(dossier, dossier_dir)
    assert verify_release_dossier(dossier_dir).passed
    assert dossier.merkle_tree.root_hash.startswith("sha256:")


def test_new_manifests_are_packaged_resources() -> None:
    root = files("intentforge").joinpath("knowledge", "topology", "families")
    assert root.joinpath("spur_gear", "manifest.yaml").is_file()
    assert root.joinpath("standard_bolt", "manifest.yaml").is_file()
