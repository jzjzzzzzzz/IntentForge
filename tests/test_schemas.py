import pytest
from pydantic import ValidationError

from intentforge.schemas import (
    Constraint,
    ConstraintGraph,
    FeaturePlan,
    FeatureStep,
    IntentSpec,
    Parameter,
    ParameterTable,
)


def test_intent_spec_supports_only_wall_mounted_bracket() -> None:
    intent = IntentSpec(
        family="wall_mounted_bracket",
        user_prompt="Create a wall-mounted bracket.",
        objective="Create an editable bracket model.",
        requirements=["Use named parameters."],
        metadata={"phase": "schema_skeleton"},
    )

    assert intent.family == "wall_mounted_bracket"
    assert intent.metadata["phase"] == "schema_skeleton"

    with pytest.raises(ValidationError):
        IntentSpec(
            family="unsupported_part",
            user_prompt="Create a gear.",
            objective="Create a gear.",
        )


def test_parameter_table_requires_unique_parameter_names() -> None:
    parameter = Parameter(
        name="back_plate_width_mm",
        value=120.0,
        unit="mm",
        description="Back plate width.",
        reason="Controls wall mounting face width.",
        min_value=1.0,
    )

    table = ParameterTable(family="wall_mounted_bracket", parameters=[parameter])

    assert table.get("back_plate_width_mm").value == 120.0

    with pytest.raises(ValidationError):
        ParameterTable(family="wall_mounted_bracket", parameters=[parameter, parameter])


def test_parameter_bounds_are_validated() -> None:
    with pytest.raises(ValidationError):
        Parameter(
            name="support_arm_length_mm",
            value=0.0,
            unit="mm",
            description="Support arm length.",
            reason="Defines projection length.",
            min_value=1.0,
        )


def test_constraint_graph_requires_unique_constraints_and_known_dependencies() -> None:
    graph = ConstraintGraph(
        family="wall_mounted_bracket",
        nodes=["back_plate_width_mm", "mounting_hole_edge_offset_x_mm"],
        dependencies={"mounting_hole_edge_offset_x_mm": ["back_plate_width_mm"]},
        constraints=[
            Constraint(
                id="hole_x_clearance",
                kind="dimensional",
                expression="mounting_hole_edge_offset_x_mm > 0",
                parameters=["mounting_hole_edge_offset_x_mm"],
                reason="Holes need side clearance.",
            )
        ],
    )

    assert graph.constraints[0].id == "hole_x_clearance"

    with pytest.raises(ValidationError):
        ConstraintGraph(
            family="wall_mounted_bracket",
            nodes=["back_plate_width_mm"],
            dependencies={"missing_node": ["back_plate_width_mm"]},
        )


def test_feature_plan_requires_ordered_dependencies_and_reasons() -> None:
    plan = FeaturePlan(
        family="wall_mounted_bracket",
        construction_strategy="Create the plate, then cut holes.",
        steps=[
            FeatureStep(
                id="create_back_plate",
                operation="extrude_box",
                parameters=["back_plate_width_mm"],
                reason="Back plate is the base datum.",
            ),
            FeatureStep(
                id="cut_mounting_holes",
                operation="cut_through_holes",
                depends_on=["create_back_plate"],
                parameters=["mounting_hole_diameter_mm"],
                reason="Holes mount the bracket to the wall.",
            ),
        ],
    )

    assert [step.id for step in plan.steps] == ["create_back_plate", "cut_mounting_holes"]

    with pytest.raises(ValidationError):
        FeaturePlan(
            family="wall_mounted_bracket",
            construction_strategy="Invalid order.",
            steps=[
                FeatureStep(
                    id="cut_mounting_holes",
                    operation="cut_through_holes",
                    depends_on=["create_back_plate"],
                    reason="Holes mount the bracket to the wall.",
                )
            ],
        )
