"""Deterministic feature planning for the supported bracket family."""

from intentforge.features import (
    feature_flags_for_parameter_table,
    is_feature_active,
    mounting_hole_pattern_from_flags,
)
from intentforge.schemas import ConstraintGraph, FeaturePlan, FeatureStep, IntentSpec, ParameterTable

SUPPORTED_FAMILY = "wall_mounted_bracket"


def plan_wall_bracket_features(parameters: ParameterTable) -> FeaturePlan:
    """Plan only active wall-mounted bracket features."""

    if parameters.family != SUPPORTED_FAMILY:
        raise ValueError(f"unsupported model family: {parameters.family}")

    feature_flags = feature_flags_for_parameter_table(parameters)
    steps = [
        FeatureStep(
            id="create_back_plate",
            operation="extrude_rounded_plate"
            if is_feature_active(feature_flags, "rounded_corners")
            else "extrude_plate",
            parameters=[
                "back_plate_width_mm",
                "back_plate_height_mm",
                "back_plate_thickness_mm",
            ]
            + (["corner_radius_mm"] if is_feature_active(feature_flags, "rounded_corners") else []),
            reason="The back plate is the wall mounting datum and base feature.",
            outputs=["back_plate_solid"],
            validation_refs=["back_plate_dimensions"],
        )
    ]

    if is_feature_active(feature_flags, "mounting_holes"):
        hole_pattern = mounting_hole_pattern_from_flags(feature_flags)
        parameters = ["mounting_hole_count", "mounting_hole_diameter_mm"]
        if hole_pattern == "rectangular_4":
            parameters.extend(["mounting_hole_spacing_x_mm", "mounting_hole_spacing_y_mm"])
        else:
            parameters.append("mounting_hole_spacing_mm")
        steps.append(
            FeatureStep(
                id="cut_mounting_holes",
                operation="cut_through_holes",
                parameters=parameters,
                depends_on=["create_back_plate"],
                reason=f"Mounting holes are active intent with pattern {hole_pattern}.",
                outputs=["mounting_holes"],
                validation_refs=["mounting_holes_symmetric", "hole_spacing_range_check"],
                metadata={"pattern": hole_pattern},
            )
        )

    if is_feature_active(feature_flags, "center_cutout"):
        steps.append(
            FeatureStep(
                id="cut_center_opening",
                operation="cut_center_rectangular_through_opening",
                parameters=["center_cutout_width_mm", "center_cutout_height_mm"],
                depends_on=["create_back_plate"],
                reason="Center cutout is active intent and should remain an editable subtractive feature.",
                outputs=["center_cutout"],
                validation_refs=["cutout_inside_plate_check"],
            )
        )

    if is_feature_active(feature_flags, "edge_fillets"):
        steps.append(
            FeatureStep(
                id="apply_edge_fillets",
                operation="fillet_exposed_edges",
                parameters=["fillet_radius_mm"],
                depends_on=[steps[-1].id],
                reason="Edge fillets are active intent and are applied after primary features.",
                outputs=["edge_fillets"],
                validation_refs=["edge_fillet_limit_check"],
            )
        )

    return FeaturePlan(
        family=SUPPORTED_FAMILY,
        construction_strategy="Create the base plate, then add only active optional features.",
        steps=steps,
        assumptions=["Optional features are controlled by parameter-table feature_flags."],
        unknowns=["No load-bearing arm or gusset feature is added until load requirements are known."],
        metadata={"planner": "deterministic", "feature_flags": feature_flags},
    )


def plan_features(
    intent: IntentSpec,
    parameters: ParameterTable,
    constraints: ConstraintGraph | None = None,
) -> FeaturePlan:
    """Plan a feature history for a supported model family."""

    if intent.family != SUPPORTED_FAMILY:
        raise ValueError(f"unsupported model family: {intent.family}")
    return plan_wall_bracket_features(parameters)
