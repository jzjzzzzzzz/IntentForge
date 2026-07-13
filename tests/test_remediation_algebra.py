"""Phase 30: Deterministic algebraic inversion tests."""

from __future__ import annotations

import pytest

from intentforge.remediation.algebra import (
    RemediationAlgebraError,
    extract_metric_to_parameter_map,
    metric_to_parameter_transform,
    normalize_inequality,
    synthesize_remediation,
)


def test_normalize_simple_inequality() -> None:
    ineq = normalize_inequality("hole_edge_distance >= 1.5 * hole_diameter")
    assert ineq.metric == "hole_edge_distance"
    assert ineq.comparison == ">="
    assert ineq.constant == 0
    assert len(ineq.terms) == 2


def test_normalize_lt_with_constant() -> None:
    ineq = normalize_inequality("cutout_area_ratio <= 0.25")
    assert ineq.metric == "cutout_area_ratio"
    assert ineq.comparison == "<="
    assert ineq.constant == -0.25


def test_normalize_multiplication_with_constant() -> None:
    ineq = normalize_inequality("minimum_section_thickness >= 2 * thickness")
    assert ineq.metric == "minimum_section_thickness"
    assert ineq.comparison == ">="


def test_normalize_rejects_compound_boolean() -> None:
    with pytest.raises(RemediationAlgebraError):
        normalize_inequality("a >= 1 and b <= 2")


def test_normalize_rejects_non_comparison() -> None:
    with pytest.raises(RemediationAlgebraError):
        normalize_inequality("a + b")


def test_metric_to_parameter_map_for_wall_family() -> None:
    mapping = extract_metric_to_parameter_map({}, family="wall_mounted_bracket")
    assert mapping["width"] == "back_plate_width_mm"
    assert mapping["hole_edge_distance"] == "back_plate_width_mm"


def test_metric_to_parameter_map_for_l_family() -> None:
    mapping = extract_metric_to_parameter_map({}, family="l_bracket")
    assert mapping["hole_edge_distance"] == "bracket_width_mm"


def test_metric_to_parameter_transform_hole_edge() -> None:
    parameters = {"back_plate_width_mm": 30.0, "mounting_hole_diameter_mm": 10.0, "mounting_hole_spacing_x_mm": 0.0}
    new_width = metric_to_parameter_transform(
        family="wall_mounted_bracket",
        metric="hole_edge_distance",
        target_metric_value=15.0,
        parameters=parameters,
    )
    assert new_width == 2 * 15 + 0 + 10


def test_metric_to_parameter_transform_rejects_unsupported() -> None:
    with pytest.raises(RemediationAlgebraError):
        metric_to_parameter_transform(
            family="unknown", metric="x", target_metric_value=0.0, parameters={},
        )


def test_synthesis_produces_deterministic_delta() -> None:
    metrics = {"hole_edge_distance": 5.0, "hole_diameter": 10.0, "hole_spacing": 0.0}
    registry = {
        "hole_edge_margin_001": {
            "id": "hole_edge_margin_001",
            "name": "Hole Edge Margin",
            "condition": {"expression": "hole_edge_distance >= 1.5 * hole_diameter"},
            "applies_to": ["wall_mounted_bracket"],
        }
    }
    parameters = {"back_plate_width_mm": 30.0, "mounting_hole_diameter_mm": 10.0, "mounting_hole_spacing_x_mm": 0.0}
    findings = [{"rule_id": "hole_edge_margin_001", "rule_name": "Hole Edge Margin"}]
    delta = synthesize_remediation(
        family="wall_mounted_bracket", parameters=parameters, metrics=metrics,
        failed_findings=findings, rule_registry=registry,
    )
    assert delta.remediation_status == "remediation_synthesized"
    assert len(delta.parameter_changes) == 1
    change = delta.parameter_changes[0]
    assert change.parameter == "back_plate_width_mm"
    assert change.delta > 0


def test_synthesis_reports_impossible_for_unknown_metric() -> None:
    metrics = {"x_unknown": 1.0}
    registry = {
        "unknown_rule": {
            "id": "unknown_rule",
            "name": "Unknown Rule",
            "condition": {"expression": "unknown_metric >= 1"},
            "applies_to": ["wall_mounted_bracket"],
        }
    }
    parameters = {"back_plate_width_mm": 100.0}
    findings = [{"rule_id": "unknown_rule", "rule_name": "Unknown Rule"}]
    delta = synthesize_remediation(
        family="wall_mounted_bracket", parameters=parameters, metrics=metrics,
        failed_findings=findings, rule_registry=registry,
    )
    assert delta.remediation_status == "remediation_impossible"
    assert all(plan.status == "remediation_impossible" for plan in delta.plans)


def test_synthesis_is_deterministic_across_runs() -> None:
    metrics = {"corner_radius": 0.5, "thickness": 8.0}
    registry = {
        "corner_radius_001": {
            "id": "corner_radius_001",
            "name": "Corner Radius",
            "condition": {"expression": "corner_radius >= 0.25 * thickness"},
            "applies_to": ["wall_mounted_bracket"],
        }
    }
    parameters = {"corner_radius_mm": 0.5, "back_plate_thickness_mm": 8.0}
    findings = [{"rule_id": "corner_radius_001", "rule_name": "Corner Radius"}]
    first = synthesize_remediation(
        family="wall_mounted_bracket", parameters=parameters, metrics=metrics,
        failed_findings=findings, rule_registry=registry,
    )
    second = synthesize_remediation(
        family="wall_mounted_bracket", parameters=parameters, metrics=metrics,
        failed_findings=findings, rule_registry=registry,
    )
    assert first.remediation_id == second.remediation_id
    assert first.proposed_parameters == second.proposed_parameters


def test_synthesis_handles_no_failures() -> None:
    metrics = {"corner_radius": 4.0, "thickness": 8.0}
    registry = {
        "corner_radius_001": {
            "id": "corner_radius_001",
            "name": "Corner Radius",
            "condition": {"expression": "corner_radius >= 0.25 * thickness"},
            "applies_to": ["wall_mounted_bracket"],
        }
    }
    parameters = {"corner_radius_mm": 4.0, "back_plate_thickness_mm": 8.0}
    delta = synthesize_remediation(
        family="wall_mounted_bracket", parameters=parameters, metrics=metrics,
        failed_findings=[], rule_registry=registry,
    )
    assert delta.remediation_status == "remediation_synthesized"
    assert delta.parameter_changes == ()


def test_synthesis_caps_cutout_area_ratio_with_width_parameter() -> None:
    metrics = {"cutout_area_ratio": 0.4, "width": 100.0, "height": 60.0}
    registry = {
        "cutout_stiffness_001": {
            "id": "cutout_stiffness_001",
            "name": "Cutout Stiffness",
            "condition": {"expression": "cutout_area_ratio <= 0.25"},
            "applies_to": ["wall_mounted_bracket"],
        }
    }
    parameters = {"center_cutout_width_mm": 50.0, "back_plate_height_mm": 60.0, "back_plate_width_mm": 100.0}
    findings = [{"rule_id": "cutout_stiffness_001", "rule_name": "Cutout Stiffness"}]
    delta = synthesize_remediation(
        family="wall_mounted_bracket", parameters=parameters, metrics=metrics,
        failed_findings=findings, rule_registry=registry,
    )
    assert delta.remediation_status == "remediation_synthesized"
    assert len(delta.parameter_changes) == 1


def test_normalize_inverted_constant() -> None:
    ineq = normalize_inequality("a <= 5 - b")
    assert ineq.metric == "a" or ineq.metric == "b"


def test_normalize_equation_constant_on_rhs() -> None:
    ineq = normalize_inequality("bracket_width >= 4 * hole_diameter")
    assert ineq.comparison == ">="


def test_engine_version_constant_is_pinned() -> None:
    from intentforge.remediation.algebra import REMEDIATION_ENGINE_VERSION
    assert isinstance(REMEDIATION_ENGINE_VERSION, str)
    assert REMEDIATION_ENGINE_VERSION == "1.0"