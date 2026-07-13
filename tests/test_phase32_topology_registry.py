"""Phase 32 registry, flange, remediation, rejection, and qualification tests."""

from __future__ import annotations

from importlib.resources import files
import json
from pathlib import Path
import subprocess
import sys

import pytest

from intentforge.assurance import build_assurance_case, build_audit_package, validate_audit_package
from intentforge.dossier import build_dossier, verify_release_dossier, write_dossier
from intentforge.knowledge.evaluator import evaluate_parameter_table
from intentforge.parser.registered_parser import (
    build_registered_intent_json_schema,
    parse_registered_intent,
    parse_registered_prompt,
)
from intentforge.remediation import synthesize_remediation
from intentforge.remediation.engine import _load_rule_registry, build_metrics
from intentforge.review import evaluate_assurance_case, get_review_policy
from intentforge.topology.expressions import evaluate_numeric_expression
from intentforge.topology.registry import RegistryManager, TopologyRegistryError, get_topology_registry
from intentforge.workflows import parse_build_intent_workflow


FLANGE_PARAMETERS = {
    "flange_outer_diameter": 190.0,
    "bolt_circle_diameter": 120.0,
    "bolt_hole_diameter": 14.0,
    "hole_count": 4,
    "flange_thickness": 20.0,
    "bore_diameter": 65.0,
    "bore_clearance": 0.5,
}


def test_registry_loads_manifests_deterministically() -> None:
    first = RegistryManager.load()
    second = RegistryManager.load()
    assert [item.topology_family for item in first.all(active_only=True)] == [
        "industrial_flange", "l_bracket", "spur_gear", "standard_bolt", "wall_mounted_bracket",
    ]
    assert first.snapshot() == second.snapshot()
    assert first.get("pipe flange").topology_family == "industrial_flange"
    with pytest.raises(TopologyRegistryError):
        first.get("unregistered_gear")


def test_flange_manifest_binds_catalog_rules_and_formula() -> None:
    manifest = get_topology_registry().get("industrial_flange")
    binding = manifest.capability_evidence_binding
    assert len(set(binding.evidence_catalog_ids)) == 65
    assert len(set(binding.rule_ids)) == 10
    mapping = manifest.metric_mapping("hole_edge_distance")
    assert mapping.expression == (
        "(flange_outer_diameter - bolt_circle_diameter) / 2.0 "
        "- (bolt_hole_diameter / 2.0)"
    )
    assert evaluate_numeric_expression(mapping.expression, FLANGE_PARAMETERS) == 28.0


def test_registered_parser_schema_and_bounds() -> None:
    parsed = parse_registered_intent({"family": "industrial_flange", "parameters": FLANGE_PARAMETERS})
    assert parsed.intent.family == "industrial_flange"
    assert len(parsed.parameter_table.parameters) == 7
    assert len(parsed.feature_plan.steps) == 3
    schema = build_registered_intent_json_schema("industrial_flange")
    assert schema["properties"]["family"]["const"] == "industrial_flange"
    assert schema["properties"]["parameters"]["properties"]["hole_count"]["type"] == "integer"
    with pytest.raises(ValueError, match="outside safe bounds"):
        parse_registered_intent({
            "family": "industrial_flange",
            "parameters": {**FLANGE_PARAMETERS, "hole_count": 100},
        })


def test_registered_natural_prompt_uses_manifest_labels() -> None:
    parsed = parse_registered_prompt(
        "industrial flange flange outer diameter 190 bolt circle diameter 120 "
        "bolt hole diameter 14 hole count 4 flange thickness 20 bore diameter 65",
        "industrial_flange",
    )
    values = {item.name: item.value for item in parsed.parameter_table.parameters}
    assert values == FLANGE_PARAMETERS


def test_dynamic_knowledge_rules_are_evaluated() -> None:
    parsed = parse_registered_intent({"family": "industrial_flange", "parameters": FLANGE_PARAMETERS})
    findings = evaluate_parameter_table(parsed.parameter_table, parsed.feature_plan)
    assert {item.rule_id for item in findings}.issubset(
        set(get_topology_registry().get("industrial_flange").capability_evidence_binding.rule_ids)
    )
    assert any(item.rule_id == "hole_edge_margin_001" and item.passed for item in findings)


def test_flange_remediation_inverts_manifest_formula() -> None:
    parameters = {**FLANGE_PARAMETERS, "flange_outer_diameter": 130.0, "bolt_circle_diameter": 110.0}
    metrics = build_metrics(parameters, family="industrial_flange")
    delta = synthesize_remediation(
        family="industrial_flange",
        parameters=parameters,
        metrics=metrics,
        failed_findings=[{"rule_id": "hole_edge_margin_001", "rule_name": "Hole Edge Margin"}],
        rule_registry=_load_rule_registry("industrial_flange"),
    )
    assert delta.remediation_status == "remediation_synthesized"
    assert [(item.parameter, item.proposed_value) for item in delta.parameter_changes] == [
        ("flange_outer_diameter", 166.0)
    ]


def test_unregistered_family_returns_content_addressed_safe_rejection(tmp_path: Path) -> None:
    first = parse_build_intent_workflow(
        {"family": "unregistered_gear", "parameters": {}}, tmp_path / "first",
    )
    second = parse_build_intent_workflow(
        {"family": "unregistered_gear", "parameters": {}}, tmp_path / "second",
    )
    envelope = first["metadata"]["safe_rejection"]
    assert first["ok"] is False and first["cad_exported"] is False
    assert envelope["state"] == "safe_rejection"
    assert envelope["safe_rejection_handling_passed"] is True
    assert envelope["geometry_success_claimed"] is False
    assert envelope["integrity"]["authentication"] == "not_cryptographically_signed"
    assert envelope["integrity"] == second["metadata"]["safe_rejection"]["integrity"]
    assert not list(tmp_path.rglob("*.step"))
    assert not list(tmp_path.rglob("*.stl"))


def test_flange_build_assurance_cas_and_dossier(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = parse_build_intent_workflow(
        {"family": "industrial_flange", "parameters": FLANGE_PARAMETERS},
        tmp_path / "build",
        request_id="phase32_flange",
    )
    assert result["ok"] and result["cad_exported"] and result["validation"]["valid"]
    case = build_assurance_case(result, profile="standard", input_request="industrial flange")
    policy = get_review_policy("intentforge_standard_design_review_v1")
    decision = evaluate_assurance_case(policy, case, result)
    package_dir = tmp_path / "package"
    package = build_audit_package(
        case, package_dir, review_policy=policy, review_decision=decision,
    )
    assert validate_audit_package(package_dir)["passed"]
    assert package["package_id"].startswith("sha256:")
    dossier = build_dossier([package_dir])
    dossier_dir = tmp_path / "dossier"
    write_dossier(dossier, dossier_dir)
    assert verify_release_dossier(dossier_dir).passed
    assert dossier.merkle_tree.root_hash.startswith("sha256:")


def test_topology_cli_and_packaged_manifests(tmp_path: Path) -> None:
    manifest = files("intentforge").joinpath(
        "knowledge", "topology", "families", "industrial_flange", "manifest.yaml",
    )
    assert manifest.is_file()
    proc = subprocess.run(
        [sys.executable, "-m", "intentforge.cli", "topology", "validate"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "./src", "PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Families checked: 5" in proc.stdout
    intent_path = tmp_path / "flange.json"
    intent_path.write_text(
        json.dumps({"family": "industrial_flange", "parameters": FLANGE_PARAMETERS}),
        encoding="utf-8",
    )
    schema = subprocess.run(
        [sys.executable, "-m", "intentforge.cli", "topology", "schema", "industrial_flange"],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "./src", "PATH": "/usr/bin:/bin"},
    )
    assert schema.returncode == 0
    assert '"flange_outer_diameter"' in schema.stdout
