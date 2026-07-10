from pathlib import Path

import yaml

from intentforge.knowledge import build_design_metrics, evaluate_design, evaluate_expression, evaluate_parameter_table
from intentforge.schemas import ParameterTable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _example_table(filename: str) -> ParameterTable:
    return ParameterTable.model_validate(
        yaml.safe_load((PROJECT_ROOT / "examples" / filename).read_text(encoding="utf-8"))
    )


def test_safe_expression_evaluator_passes_basic_rule() -> None:
    metrics = {"hole_edge_distance": 12.0, "hole_diameter": 6.0}

    assert evaluate_expression("hole_edge_distance >= 1.5 * hole_diameter", metrics) is True


def test_wall_bracket_example_produces_passing_findings() -> None:
    table = _example_table("bracket_params.yaml")

    findings = evaluate_parameter_table(table)

    assert findings
    assert all(finding.passed for finding in findings)


def test_invalid_hole_edge_distance_produces_finding() -> None:
    metrics = {
        "hole_edge_distance": 4.0,
        "hole_diameter": 6.0,
        "hole_spacing": 24.0,
        "mounting_holes_active": True,
        "fastener_edge_clearance": 4.0,
        "bracket_width": 120.0,
        "rounded_corners_active": False,
        "center_cutout_active": False,
        "tool_clearance": 6.0,
        "active_optional_feature_count": 1,
        "minimum_section_thickness": 50.0,
        "thickness": 6.0,
    }

    findings = evaluate_design("wall_mounted_bracket", metrics)
    edge_finding = next(finding for finding in findings if finding.rule_id == "hole_edge_margin_001")

    assert edge_finding.passed is False
    assert "edge distance" in edge_finding.message.lower()


def test_l_bracket_without_gusset_can_receive_recommendation() -> None:
    table = _example_table("l_bracket_params.yaml")
    metrics = build_design_metrics(table)

    findings = evaluate_parameter_table(table)
    gusset_finding = next(finding for finding in findings if finding.rule_id == "gusset_recommendation_001")

    assert metrics["vertical_leg_height_to_thickness"] > 12
    assert gusset_finding.passed is False
    assert "gusset" in gusset_finding.recommendation.lower()
