import json
from pathlib import Path

import pytest
import yaml

from intentforge.features import feature_flags_for_parameter_table, make_mounting_hole_flag
from intentforge.parser import parse_prompt
from intentforge.schemas import ConstraintGraph, FeaturePlan, IntentSpec, ParameterTable
from intentforge.validator.intent_validator import validate_wall_bracket_intent


EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _load_intent() -> IntentSpec:
    return IntentSpec.model_validate(json.loads((EXAMPLES_DIR / "bracket_intent.json").read_text()))


def _load_parameter_table() -> ParameterTable:
    return ParameterTable.model_validate(yaml.safe_load((EXAMPLES_DIR / "bracket_params.yaml").read_text()))


def _load_feature_plan() -> FeaturePlan:
    return FeaturePlan.model_validate(json.loads((EXAMPLES_DIR / "bracket_feature_plan.json").read_text()))


def _load_constraint_graph() -> ConstraintGraph:
    return ConstraintGraph.model_validate(json.loads((EXAMPLES_DIR / "bracket_constraints.json").read_text()))


def _check(report, check_id: str):
    checks = {check.id: check for check in report.checks}
    return checks[check_id]


def test_default_bracket_intent_passes() -> None:
    report = validate_wall_bracket_intent(
        _load_intent(),
        _load_parameter_table(),
        _load_feature_plan(),
        _load_constraint_graph(),
    )

    assert report.valid is True
    assert report.failed_checks == []


def test_missing_required_parameter_fails_intent_validation() -> None:
    table = _load_parameter_table()
    table = table.model_copy(
        update={
            "parameters": [
                parameter
                for parameter in table.parameters
                if parameter.name != "mounting_hole_spacing_mm"
            ]
        }
    )

    report = validate_wall_bracket_intent(
        _load_intent(),
        table,
        _load_feature_plan(),
        _load_constraint_graph(),
    )

    assert report.valid is False
    assert _check(report, "required_parameters_exist_check").passed is False


def test_missing_base_plate_feature_fails_intent_validation() -> None:
    feature_plan = _load_feature_plan()
    feature_plan = feature_plan.model_copy(
        update={
            "steps": [
                step.model_copy(update={"depends_on": []})
                for step in feature_plan.steps
                if step.id != "create_back_plate"
            ]
        }
    )

    report = validate_wall_bracket_intent(
        _load_intent(),
        _load_parameter_table(),
        feature_plan,
        _load_constraint_graph(),
    )

    assert report.valid is False
    assert _check(report, "required_feature_steps_exist_check").passed is False


def test_mounting_holes_without_symmetry_constraint_fails() -> None:
    constraint_graph = _load_constraint_graph()
    constraint_graph = constraint_graph.model_copy(
        update={
            "constraints": [
                constraint
                for constraint in constraint_graph.constraints
                if constraint.id != "mounting_holes_symmetric"
            ],
            "assumptions": [],
        }
    )

    report = validate_wall_bracket_intent(
        _load_intent(),
        _load_parameter_table(),
        _load_feature_plan(),
        constraint_graph,
    )

    assert report.valid is False
    assert _check(report, "mounting_holes_symmetric_check").passed is False


def test_feature_plan_with_cuts_before_base_plate_fails() -> None:
    feature_plan = _load_feature_plan()
    cut_holes = feature_plan.steps[1].model_copy(update={"depends_on": []})
    base_plate = feature_plan.steps[0]
    center_cutout = feature_plan.steps[2].model_copy(update={"depends_on": ["create_back_plate"]})
    feature_plan = FeaturePlan(
        family="wall_mounted_bracket",
        construction_strategy="Invalid order for validation.",
        steps=[cut_holes, base_plate, center_cutout],
    )

    report = validate_wall_bracket_intent(
        _load_intent(),
        _load_parameter_table(),
        feature_plan,
        _load_constraint_graph(),
    )

    assert report.valid is False
    assert _check(report, "feature_history_base_before_cuts_check").passed is False


def test_no_cutout_intent_passes_without_cutout_feature() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.")

    report = validate_wall_bracket_intent(
        parsed.intent,
        parsed.parameter_table,
        parsed.feature_plan,
        parsed.constraint_graph,
    )

    assert report.valid is True
    assert _check(report, "center_cutout_intent_feature_check").passed is True
    assert "cut_center_opening" not in {step.id for step in parsed.feature_plan.steps}


def test_requested_cutout_missing_from_feature_plan_fails() -> None:
    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes and a center cutout."
    )
    feature_plan = parsed.feature_plan.model_copy(
        update={
            "steps": [
                step
                for step in parsed.feature_plan.steps
                if step.id != "cut_center_opening"
            ]
        }
    )

    report = validate_wall_bracket_intent(
        parsed.intent,
        parsed.parameter_table,
        feature_plan,
        parsed.constraint_graph,
    )

    assert report.valid is False
    assert _check(report, "center_cutout_intent_feature_check").passed is False


def test_four_hole_pattern_passes_intent_validation() -> None:
    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide and 60 mm tall with four corner screw holes."
    )

    report = validate_wall_bracket_intent(
        parsed.intent,
        parsed.parameter_table,
        parsed.feature_plan,
        parsed.constraint_graph,
    )

    assert report.valid is True
    assert _check(report, "mounting_hole_pattern_check").passed is True


def test_unsupported_hole_count_fails_intent_validation() -> None:
    parsed = parse_prompt("Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes.")
    flags = feature_flags_for_parameter_table(parsed.parameter_table)
    flags["mounting_holes"] = make_mounting_hole_flag("requested_by_user", "Unsupported test pattern.", 3)
    table = parsed.parameter_table.model_copy(
        update={
            "parameters": [
                parameter.model_copy(update={"value": 3})
                if parameter.name == "mounting_hole_count"
                else parameter
                for parameter in parsed.parameter_table.parameters
            ],
            "metadata": {**parsed.parameter_table.metadata, "feature_flags": flags},
        }
    )
    intent = parsed.intent.model_copy(update={"metadata": {**parsed.intent.metadata, "feature_flags": flags}})

    report = validate_wall_bracket_intent(
        intent,
        table,
        parsed.feature_plan,
        parsed.constraint_graph,
    )

    assert report.valid is False
    assert _check(report, "mounting_hole_pattern_check").passed is False


def test_feature_plan_pattern_mismatch_fails_intent_validation() -> None:
    parsed = parse_prompt(
        "Make a wall-mounted bracket 120 mm wide and 60 mm tall with four corner screw holes."
    )
    feature_plan = parsed.feature_plan.model_copy(
        update={
            "steps": [
                step.model_copy(update={"metadata": {**step.metadata, "pattern": "symmetric_2_horizontal"}})
                if step.id == "cut_mounting_holes"
                else step
                for step in parsed.feature_plan.steps
            ]
        }
    )

    report = validate_wall_bracket_intent(
        parsed.intent,
        parsed.parameter_table,
        feature_plan,
        parsed.constraint_graph,
    )

    assert report.valid is False
    assert _check(report, "mounting_hole_pattern_check").passed is False
