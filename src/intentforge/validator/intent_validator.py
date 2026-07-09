"""Intent consistency validation for wall-mounted bracket models."""

from __future__ import annotations

from typing import Any

from intentforge.features import (
    feature_flags_for_parameter_table,
    hole_pattern_for_count,
    is_feature_active,
    mounting_hole_count_from_flags,
    mounting_hole_pattern_from_flags,
    normalize_feature_flags,
)
from intentforge.schemas import (
    ConstraintGraph,
    FeaturePlan,
    FeatureStep,
    IntentSpec,
    ParameterTable,
    ValidationCheck,
    ValidationReport,
)

SUPPORTED_FAMILY = "wall_mounted_bracket"
L_BRACKET_FAMILY = "l_bracket"

REQUIRED_PARAMETERS = [
    "back_plate_width_mm",
    "back_plate_height_mm",
    "back_plate_thickness_mm",
]

FEATURE_REQUIRED_PARAMETERS = {
    "mounting_holes": ["mounting_hole_count", "mounting_hole_diameter_mm"],
    "center_cutout": ["center_cutout_width_mm", "center_cutout_height_mm"],
    "rounded_corners": ["corner_radius_mm"],
    "edge_fillets": ["fillet_radius_mm"],
}

FEATURE_REQUIRED_CONSTRAINTS = {
    "mounting_holes": ["mounting_holes_symmetric", "hole_spacing_fits_plate"],
    "center_cutout": ["center_cutout_fits_plate_width", "center_cutout_fits_plate_height"],
    "rounded_corners": ["corner_radius_fits_plate"],
    "edge_fillets": ["fillet_smaller_than_thickness"],
}


def _make_check(
    check_id: str,
    description: str,
    passed: bool,
    expected: Any = None,
    actual: Any = None,
    explanation: str = "",
    related_parameters: list[str] | None = None,
    related_features: list[str] | None = None,
    severity: str = "error",
) -> ValidationCheck:
    status = "pass" if passed else ("warning" if severity == "warning" else "fail")
    return ValidationCheck(
        id=check_id,
        description=description,
        status=status,
        severity=severity,
        expected_value=str(expected) if expected is not None and not isinstance(expected, int | float | str | bool) else expected,
        measured_value=str(actual) if actual is not None and not isinstance(actual, int | float | str | bool) else actual,
        related_parameters=related_parameters or [],
        related_features=related_features or [],
        message=explanation,
    )


def _step_text(step: FeatureStep) -> str:
    parts = [
        step.id,
        step.operation,
        step.reason,
        " ".join(step.parameters),
        " ".join(step.outputs),
        " ".join(step.validation_refs),
    ]
    return " ".join(parts).lower()


def _find_base_step(steps: list[FeatureStep]) -> FeatureStep | None:
    for step in steps:
        text = _step_text(step)
        if "back_plate" in text or "base_plate" in text or "plate" in text and "extrude" in text:
            return step
    return None


def _find_mounting_hole_step(steps: list[FeatureStep]) -> FeatureStep | None:
    for step in steps:
        text = _step_text(step)
        if "mounting" in text and "hole" in text:
            return step
    return None


def _find_center_cutout_step(steps: list[FeatureStep]) -> FeatureStep | None:
    for step in steps:
        text = _step_text(step)
        if ("center" in text or "centred" in text) and ("cutout" in text or "opening" in text):
            return step
    return None


def _cut_step_ids_before_base(feature_plan: FeaturePlan) -> list[str]:
    steps = feature_plan.steps
    base_step = _find_base_step(steps)
    if base_step is None:
        return [step.id for step in steps if "cut" in _step_text(step)]

    base_index = steps.index(base_step)
    return [
        step.id
        for index, step in enumerate(steps)
        if index < base_index and ("cut" in step.operation.lower() or "cut" in step.id.lower())
    ]


def _intent_mentions_center_cutout(intent: IntentSpec) -> bool:
    text = " ".join(
        [intent.user_prompt, intent.objective, *intent.requirements, *intent.assumptions]
    ).lower()
    return ("cutout" in text or "opening" in text) and ("center" in text or "centred" in text)


def _constraint_text(constraint_graph: ConstraintGraph) -> str:
    parts: list[str] = []
    for constraint in constraint_graph.constraints:
        parts.extend([constraint.id, constraint.expression, constraint.reason])
    parts.extend(constraint_graph.assumptions)
    return " ".join(parts).lower()


def _feature_flags(
    intent: IntentSpec,
    parameter_table: ParameterTable | None,
    feature_plan: FeaturePlan | None,
) -> dict[str, dict[str, str]]:
    raw_flags = intent.metadata.get("feature_flags")
    if isinstance(raw_flags, dict):
        return normalize_feature_flags(raw_flags, intent.family)
    if parameter_table is not None:
        return feature_flags_for_parameter_table(parameter_table)
    if feature_plan is not None and isinstance(feature_plan.metadata.get("feature_flags"), dict):
        return normalize_feature_flags(feature_plan.metadata["feature_flags"], feature_plan.family)
    return normalize_feature_flags(None, intent.family)


def _required_parameters(feature_flags: dict[str, dict[str, str]]) -> list[str]:
    required = list(REQUIRED_PARAMETERS)
    for feature, names in FEATURE_REQUIRED_PARAMETERS.items():
        if is_feature_active(feature_flags, feature):
            required.extend(names)
            if feature == "mounting_holes":
                pattern = mounting_hole_pattern_from_flags(feature_flags)
                if pattern == "rectangular_4":
                    required.extend(["mounting_hole_spacing_x_mm", "mounting_hole_spacing_y_mm"])
                else:
                    required.append("mounting_hole_spacing_mm")
    return required


def _required_constraints(feature_flags: dict[str, dict[str, str]]) -> list[str]:
    required: list[str] = []
    for feature, names in FEATURE_REQUIRED_CONSTRAINTS.items():
        if is_feature_active(feature_flags, feature):
            required.extend(names)
            if feature == "mounting_holes" and mounting_hole_pattern_from_flags(feature_flags) == "rectangular_4":
                required.append("hole_spacing_y_fits_plate")
    return required


def _hole_count(parameter_table: ParameterTable | None, feature_flags: dict[str, dict[str, str]]) -> int:
    if parameter_table is not None:
        try:
            value = parameter_table.get("mounting_hole_count").value
            if isinstance(value, int | float) and not isinstance(value, bool):
                return int(value)
        except KeyError:
            pass
    return mounting_hole_count_from_flags(feature_flags)


def validate_wall_bracket_intent(
    intent: IntentSpec,
    parameter_table: ParameterTable | None = None,
    feature_plan: FeaturePlan | None = None,
    constraint_graph: ConstraintGraph | None = None,
) -> ValidationReport:
    """Validate structured design intent consistency for a wall-mounted bracket."""

    checks: list[ValidationCheck] = []
    feature_flags = _feature_flags(intent, parameter_table, feature_plan)
    mounting_holes_active = is_feature_active(feature_flags, "mounting_holes")
    center_cutout_active = is_feature_active(feature_flags, "center_cutout")
    hole_count = _hole_count(parameter_table, feature_flags)
    hole_pattern = mounting_hole_pattern_from_flags(feature_flags)
    required_parameters = _required_parameters(feature_flags)
    required_constraints = _required_constraints(feature_flags)

    object_type_ok = intent.family == SUPPORTED_FAMILY
    checks.append(
        _make_check(
            "object_type_check",
            "Intent object type is wall_mounted_bracket.",
            object_type_ok,
            expected=SUPPORTED_FAMILY,
            actual=intent.family,
            explanation=(
                "Intent uses the supported wall-mounted bracket family."
                if object_type_ok
                else f"Unsupported intent family: {intent.family}"
            ),
        )
    )

    if parameter_table is None:
        checks.append(
            _make_check(
                "required_parameters_exist_check",
                "All required bracket parameters exist.",
                False,
                expected=required_parameters,
                actual="no parameter table provided",
                explanation="Cannot validate required parameters without a parameter table.",
            )
        )
    else:
        parameter_names = set(parameter_table.by_name())
        missing_parameters = []
        for name in required_parameters:
            if name == "mounting_hole_spacing_mm" and "mounting_hole_spacing_x_mm" in parameter_names:
                continue
            if name not in parameter_names:
                missing_parameters.append(name)
        checks.append(
            _make_check(
                "required_parameters_exist_check",
                "All required bracket parameters exist.",
                not missing_parameters,
                expected=required_parameters,
                actual=sorted(parameter_names),
                explanation=(
                    "All required parameters are present."
                    if not missing_parameters
                    else f"Missing required parameters: {', '.join(missing_parameters)}"
                ),
                related_parameters=required_parameters,
            )
        )

    if feature_plan is None:
        checks.extend(
            [
                _make_check(
                    "required_feature_steps_exist_check",
                    "Required bracket feature steps exist.",
                    False,
                    expected="active feature steps",
                    actual="no feature plan provided",
                    explanation="Cannot validate feature steps without a feature plan.",
                ),
                _make_check(
                    "feature_history_base_before_cuts_check",
                    "Base plate feature appears before cut features.",
                    False,
                    expected="base plate before cuts",
                    actual="no feature plan provided",
                    explanation="Cannot validate feature history without a feature plan.",
                ),
                _make_check(
                    "center_cutout_intent_feature_check",
                    "Center cutout intent is represented in the feature plan.",
                    False,
                    expected="center cutout feature when intent asks for one",
                    actual="no feature plan provided",
                    explanation="Cannot validate cutout intent without a feature plan.",
                ),
            ]
        )
    else:
        base_step = _find_base_step(feature_plan.steps)
        mounting_hole_step = _find_mounting_hole_step(feature_plan.steps)
        center_cutout_step = _find_center_cutout_step(feature_plan.steps)
        missing_steps = []
        if base_step is None:
            missing_steps.append("base plate")
        if mounting_holes_active and mounting_hole_step is None:
            missing_steps.append("mounting holes")
        if center_cutout_active and center_cutout_step is None:
            missing_steps.append("center cutout")

        checks.append(
            _make_check(
                "required_feature_steps_exist_check",
                "Required bracket feature steps exist.",
                not missing_steps,
                expected="base plate plus active optional feature steps",
                actual=[step.id for step in feature_plan.steps],
                explanation=(
                    "Required feature steps are present."
                    if not missing_steps
                    else f"Missing required feature steps: {', '.join(missing_steps)}"
                ),
                related_features=[step.id for step in feature_plan.steps],
            )
        )

        expected_hole_pattern = hole_pattern_for_count(hole_count)
        feature_plan_pattern = (
            mounting_hole_step.metadata.get("pattern")
            if mounting_hole_step is not None
            else None
        )
        pattern_ok = (
            not mounting_holes_active
            or (
                expected_hole_pattern is not None
                and hole_pattern == expected_hole_pattern
                and feature_plan_pattern == expected_hole_pattern
            )
        )
        checks.append(
            _make_check(
                "mounting_hole_pattern_check",
                "Mounting-hole count, feature flag pattern, and feature plan pattern agree.",
                pattern_ok,
                expected="2/symmetric_2_horizontal or 4/rectangular_4",
                actual=(
                    "omitted"
                    if not mounting_holes_active
                    else f"{hole_count}/{hole_pattern}/plan={feature_plan_pattern}"
                ),
                explanation=(
                    "Mounting holes are omitted, so no pattern is required."
                    if not mounting_holes_active
                    else f"Mounting-hole pattern {hole_pattern} matches count {hole_count} and feature plan."
                    if pattern_ok
                    else "Mounting-hole count, feature flag pattern, and feature plan pattern do not agree."
                ),
                related_features=[mounting_hole_step.id] if mounting_hole_step else [],
                related_parameters=["mounting_hole_count"],
            )
        )

        cuts_before_base = _cut_step_ids_before_base(feature_plan)
        checks.append(
            _make_check(
                "feature_history_base_before_cuts_check",
                "Base plate feature appears before cut features.",
                not cuts_before_base and base_step is not None,
                expected="base plate before cuts",
                actual=(
                    "base plate before cuts"
                    if not cuts_before_base and base_step is not None
                    else f"cuts before base plate: {', '.join(cuts_before_base) or 'base plate missing'}"
                ),
                explanation=(
                    "Feature history creates the base plate before subtractive cuts."
                    if not cuts_before_base and base_step is not None
                    else "Feature history has cut operations before the base plate is established."
                ),
                related_features=[step.id for step in feature_plan.steps],
            )
        )

        intent_needs_cutout = center_cutout_active or _intent_mentions_center_cutout(intent)
        cutout_ok = not intent_needs_cutout or center_cutout_step is not None
        checks.append(
            _make_check(
                "center_cutout_intent_feature_check",
                "Center cutout intent is represented in the feature plan.",
                cutout_ok,
                expected="center cutout feature when intent asks for one",
                actual=center_cutout_step.id if center_cutout_step else "missing",
                explanation=(
                    "Center cutout intent is represented in the feature plan."
                    if cutout_ok
                    else "Intent requests a centered cutout, but the feature plan does not include one."
                ),
                related_features=[center_cutout_step.id] if center_cutout_step else [],
            )
        )

    if constraint_graph is None:
        checks.extend(
            [
                _make_check(
                    "required_constraints_exist_check",
                    "Required bracket intent constraints exist.",
                    False,
                    expected=required_constraints,
                    actual="no constraint graph provided",
                    explanation="Cannot validate constraints without a constraint graph.",
                ),
                _make_check(
                    "mounting_holes_symmetric_check",
                    "Mounting holes are explicitly marked symmetric.",
                    not mounting_holes_active,
                    expected="symmetric mounting-hole constraint",
                    actual="no constraint graph provided",
                    explanation=(
                        "Mounting holes are omitted, so symmetry is not required."
                        if not mounting_holes_active
                        else "Cannot validate mounting-hole symmetry without a constraint graph."
                    ),
                ),
            ]
        )
    else:
        constraint_ids = {constraint.id for constraint in constraint_graph.constraints}
        missing_constraints = [name for name in required_constraints if name not in constraint_ids]
        checks.append(
            _make_check(
                "required_constraints_exist_check",
                "Required bracket intent constraints exist.",
                not missing_constraints,
                expected=required_constraints,
                actual=sorted(constraint_ids),
                explanation=(
                    "Required intent constraints are present."
                    if not missing_constraints
                    else f"Missing required constraints: {', '.join(missing_constraints)}"
                ),
            )
        )

        symmetric_marked = not mounting_holes_active or any(
            constraint.id == "mounting_holes_symmetric"
            or ("mounting" in constraint.id and "symmetr" in constraint.id)
            for constraint in constraint_graph.constraints
        )
        checks.append(
            _make_check(
                "mounting_holes_symmetric_check",
                "Mounting holes are explicitly marked symmetric.",
                symmetric_marked,
                expected="constraint or assumption states mounting-hole symmetry when mounting holes are active",
                actual="symmetric or omitted" if symmetric_marked else "not marked symmetric",
                explanation=(
                    "Mounting holes are omitted, so symmetry is not required."
                    if not mounting_holes_active
                    else "Mounting-hole symmetry is explicitly preserved in constraints."
                    if symmetric_marked
                    else "Mounting holes are not explicitly marked as symmetric in the constraint graph."
                ),
            )
        )

    failed_count = sum(1 for check in checks if check.status == "fail")
    warning_count = sum(1 for check in checks if check.status == "warning")
    passed_count = sum(1 for check in checks if check.status in {"pass", "warning"})
    summary = (
        f"Intent validation completed: {passed_count}/{len(checks)} checks passed, "
        f"{failed_count} failed, {warning_count} warnings."
    )

    return ValidationReport(
        family=SUPPORTED_FAMILY,
        checks=checks,
        summary=summary,
        metadata={"validator": "intent", "feature_flags": feature_flags},
    )


def _l_required_parameters(feature_flags: dict[str, dict[str, Any]]) -> list[str]:
    required = ["base_leg_length_mm", "vertical_leg_length_mm", "bracket_width_mm", "thickness_mm"]
    if is_feature_active(feature_flags, "base_mounting_holes") or is_feature_active(feature_flags, "vertical_mounting_holes"):
        required.append("hole_diameter_mm")
    if is_feature_active(feature_flags, "base_mounting_holes"):
        required.extend(["base_hole_count", "base_hole_spacing_mm"])
    if is_feature_active(feature_flags, "vertical_mounting_holes"):
        required.extend(["vertical_hole_count", "vertical_hole_spacing_mm"])
    if is_feature_active(feature_flags, "inside_fillet"):
        required.append("inside_fillet_radius_mm")
    if is_feature_active(feature_flags, "outside_edge_fillets"):
        required.append("outside_edge_fillet_radius_mm")
    if is_feature_active(feature_flags, "triangular_gusset"):
        required.extend(["gusset_enabled", "gusset_thickness_mm", "gusset_height_mm"])
    return required


def _l_hole_count(parameter_table: ParameterTable | None, name: str) -> int:
    if parameter_table is None:
        return 0
    try:
        value = parameter_table.get(name).value
    except KeyError:
        return 0
    if isinstance(value, int | float) and not isinstance(value, bool):
        return int(value)
    return -1


def validate_l_bracket_intent(
    intent: IntentSpec,
    parameter_table: ParameterTable | None = None,
    feature_plan: FeaturePlan | None = None,
    constraint_graph: ConstraintGraph | None = None,
) -> ValidationReport:
    """Validate structured design intent consistency for an L-bracket."""

    checks: list[ValidationCheck] = []
    feature_flags = _feature_flags(intent, parameter_table, feature_plan)
    required_parameters = _l_required_parameters(feature_flags)

    checks.append(
        _make_check(
            "object_type_check",
            "Intent object type is l_bracket.",
            intent.family == L_BRACKET_FAMILY,
            expected=L_BRACKET_FAMILY,
            actual=intent.family,
            explanation=(
                "Intent uses the supported L-bracket family."
                if intent.family == L_BRACKET_FAMILY
                else f"Unsupported intent family: {intent.family}"
            ),
        )
    )

    if parameter_table is None:
        checks.append(
            _make_check(
                "required_parameters_exist_check",
                "All required L-bracket parameters exist.",
                False,
                expected=required_parameters,
                actual="no parameter table provided",
                explanation="Cannot validate required parameters without a parameter table.",
            )
        )
    else:
        parameter_names = set(parameter_table.by_name())
        missing = [name for name in required_parameters if name not in parameter_names]
        checks.append(
            _make_check(
                "required_parameters_exist_check",
                "All required L-bracket parameters exist.",
                not missing,
                expected=required_parameters,
                actual=sorted(parameter_names),
                explanation="All required parameters are present." if not missing else f"Missing required parameters: {', '.join(missing)}",
                related_parameters=required_parameters,
            )
        )

    if feature_plan is None:
        checks.append(
            _make_check(
                "required_feature_steps_exist_check",
                "Required L-bracket feature steps exist.",
                False,
                expected="base leg, vertical leg, right-angle join, and active optional steps",
                actual="no feature plan provided",
                explanation="Cannot validate L-bracket feature steps without a feature plan.",
            )
        )
    else:
        step_ids = [step.id for step in feature_plan.steps]
        required_steps = ["create_base_leg", "create_vertical_leg", "join_legs_at_right_angle"]
        if is_feature_active(feature_flags, "base_mounting_holes"):
            required_steps.append("cut_base_mounting_holes")
        if is_feature_active(feature_flags, "vertical_mounting_holes"):
            required_steps.append("cut_vertical_mounting_holes")
        if is_feature_active(feature_flags, "triangular_gusset"):
            required_steps.append("add_triangular_gusset")
        missing_steps = [step for step in required_steps if step not in step_ids]
        checks.append(
            _make_check(
                "required_feature_steps_exist_check",
                "Required L-bracket feature steps exist.",
                not missing_steps,
                expected=required_steps,
                actual=step_ids,
                explanation="Required feature steps are present." if not missing_steps else f"Missing required feature steps: {', '.join(missing_steps)}",
                related_features=step_ids,
            )
        )
        order_ok = True
        order_reason = "Feature history creates both legs before cuts, gussets, or fillets."
        try:
            join_index = step_ids.index("join_legs_at_right_angle")
            for cut_step in ["cut_base_mounting_holes", "cut_vertical_mounting_holes", "add_triangular_gusset", "add_inside_fillet", "add_outside_edge_fillets"]:
                if cut_step in step_ids and step_ids.index(cut_step) < join_index:
                    order_ok = False
                    order_reason = f"{cut_step} appears before join_legs_at_right_angle."
                    break
        except ValueError:
            order_ok = False
            order_reason = "join_legs_at_right_angle is missing."
        checks.append(
            _make_check(
                "feature_history_legs_before_cuts_check",
                "L-bracket solids are created and joined before cuts and optional details.",
                order_ok,
                expected="create legs, join, then cuts/gusset/fillets",
                actual=step_ids,
                explanation=order_reason,
                related_features=step_ids,
            )
        )

    hole_failures: list[str] = []
    if is_feature_active(feature_flags, "base_mounting_holes") and _l_hole_count(parameter_table, "base_hole_count") != 2:
        hole_failures.append("base_hole_count must be 2 when base holes are active")
    if is_feature_active(feature_flags, "vertical_mounting_holes") and _l_hole_count(parameter_table, "vertical_hole_count") != 2:
        hole_failures.append("vertical_hole_count must be 2 when vertical holes are active")
    checks.append(
        _make_check(
            "l_hole_count_intent_check",
            "Active L-bracket hole features use supported counts.",
            not hole_failures,
            expected="0 or 2 holes per leg",
            actual="valid" if not hole_failures else "; ".join(hole_failures),
            explanation="Hole-count intent is valid." if not hole_failures else "; ".join(hole_failures),
            related_features=["base_mounting_holes", "vertical_mounting_holes"],
        )
    )

    if constraint_graph is not None:
        constraint_ids = {constraint.id for constraint in constraint_graph.constraints}
        required_constraints = {"l_bracket_right_angle"}
        if is_feature_active(feature_flags, "base_mounting_holes"):
            required_constraints.add("base_holes_fit_leg")
        if is_feature_active(feature_flags, "vertical_mounting_holes"):
            required_constraints.add("vertical_holes_fit_leg")
        if is_feature_active(feature_flags, "triangular_gusset"):
            required_constraints.add("gusset_fits_inside_corner")
        missing_constraints = sorted(required_constraints - constraint_ids)
        checks.append(
            _make_check(
                "required_constraints_exist_check",
                "Required L-bracket intent constraints exist.",
                not missing_constraints,
                expected=sorted(required_constraints),
                actual=sorted(constraint_ids),
                explanation="Required constraints are present." if not missing_constraints else f"Missing required constraints: {', '.join(missing_constraints)}",
            )
        )

    failed_count = sum(1 for check in checks if check.status == "fail")
    warning_count = sum(1 for check in checks if check.status == "warning")
    passed_count = sum(1 for check in checks if check.status in {"pass", "warning"})
    summary = (
        f"L-bracket intent validation completed: {passed_count}/{len(checks)} checks passed, "
        f"{failed_count} failed, {warning_count} warnings."
    )
    return ValidationReport(
        family=L_BRACKET_FAMILY,
        checks=checks,
        summary=summary,
        metadata={"validator": "intent", "feature_flags": feature_flags},
    )


def validate_intent(
    intent: IntentSpec,
    parameter_table: ParameterTable | None = None,
    feature_plan: FeaturePlan | None = None,
    constraint_graph: ConstraintGraph | None = None,
) -> ValidationReport:
    """Validate structured intent before or after planning."""

    if intent.family == L_BRACKET_FAMILY:
        return validate_l_bracket_intent(intent, parameter_table, feature_plan, constraint_graph)
    return validate_wall_bracket_intent(intent, parameter_table, feature_plan, constraint_graph)
