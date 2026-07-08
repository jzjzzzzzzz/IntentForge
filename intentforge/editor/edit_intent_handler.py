"""Structured edit-intent handling for wall-mounted bracket parameters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from intentforge.features import (
    L_BRACKET_FEATURES,
    OPTIONAL_FEATURES,
    feature_flags_for_parameter_table,
    feature_for_parameter,
    hole_pattern_for_count,
    is_feature_active,
    make_feature_flag,
    make_mounting_hole_flag,
    mounting_hole_count_from_flags,
    normalize_feature_flags,
)
from intentforge.generator.cadquery_generator import build_l_bracket, build_wall_bracket
from intentforge.parameters.aliases import canonical_intent_name, canonical_parameter_name
from intentforge.schemas import ConstraintGraph, EditReport, EditRequest, Parameter, ParameterTable
from intentforge.validator.geometry_validator import validate_l_bracket, validate_wall_bracket

SUPPORTED_FAMILY = "wall_mounted_bracket"
L_BRACKET_FAMILY = "l_bracket"
DEFAULT_MIN_EDGE_DISTANCE_MM = 3.0
CONSTRAINT_CHECK_IDS = {
    "object_family_check",
    "parameter_range_check",
    "hole_spacing_range_check",
    "hole_pattern_check",
    "hole_diameter_range_check",
    "cutout_inside_plate_check",
    "corner_radius_limit_check",
    "edge_fillet_limit_check",
}

CONSTRAINT_FAILURE_PREFIXES = {
    "hole_spacing_range_check": "invalid hole spacing",
    "hole_diameter_range_check": "invalid hole diameter",
    "cutout_inside_plate_check": "oversized cutout",
    "corner_radius_limit_check": "corner radius too large",
    "edge_fillet_limit_check": "edge fillet radius too large",
}


def _normalise_edit_request(edit_request: dict[str, Any] | EditRequest) -> tuple[list[dict[str, Any]], list[str]]:
    if isinstance(edit_request, EditRequest):
        edits = [
            {"type": "set_parameter", "parameter": parameter, "value": value}
            for parameter, value in edit_request.parameter_updates.items()
        ]
        preserve = edit_request.preserve_intent
        return edits, preserve

    if not isinstance(edit_request, dict):
        return [], []

    edits = edit_request.get("edits", [])
    preserve = edit_request.get("preserve", [])
    if not isinstance(edits, list):
        edits = []
    if not isinstance(preserve, list):
        preserve = []
    return edits, [str(item) for item in preserve]


def _min_edge_distance(constraints: ConstraintGraph | None) -> float:
    if constraints is None:
        return DEFAULT_MIN_EDGE_DISTANCE_MM

    value = constraints.metadata.get("min_edge_distance_mm")
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)

    for constraint in constraints.constraints:
        constraint_value = constraint.metadata.get("min_edge_distance_mm")
        if isinstance(constraint_value, int | float) and not isinstance(constraint_value, bool):
            return float(constraint_value)

    return DEFAULT_MIN_EDGE_DISTANCE_MM


def _with_constraint_metadata(parameter_table: ParameterTable, constraints: ConstraintGraph | None) -> ParameterTable:
    metadata = dict(parameter_table.metadata)
    metadata["min_edge_distance_mm"] = _min_edge_distance(constraints)
    return parameter_table.model_copy(update={"metadata": metadata})


def _with_feature_flags(
    parameter_table: ParameterTable,
    feature_flags: dict[str, dict[str, str]],
) -> ParameterTable:
    metadata = dict(parameter_table.metadata)
    metadata["feature_flags"] = normalize_feature_flags(feature_flags)
    return parameter_table.model_copy(update={"metadata": metadata})


def _has_symmetry_constraint(constraints: ConstraintGraph | None) -> bool:
    if constraints is None:
        return False
    return any(
        constraint.id == "mounting_holes_symmetric"
        or ("mounting" in constraint.id and "symmetr" in constraint.id)
        for constraint in constraints.constraints
    )


def _constraint_failures(parameter_table: ParameterTable, constraints: ConstraintGraph | None) -> list[str]:
    table_for_validation = _with_constraint_metadata(parameter_table, constraints)
    report = validate_wall_bracket(None, table_for_validation)
    failures: list[str] = []
    feature_flags = feature_flags_for_parameter_table(parameter_table)
    if is_feature_active(feature_flags, "mounting_holes"):
        try:
            hole_count = parameter_table.get("mounting_hole_count").value
        except KeyError:
            hole_count = 2
        if isinstance(hole_count, bool) or not isinstance(hole_count, int | float):
            failures.append("invalid hole count: mounting_hole_count must be numeric")
        elif int(hole_count) not in {2, 4}:
            failures.append(
                "unsupported hole count: mounting_hole_count must be 2 or 4"
            )
    for check in report.failed_checks:
        if check.id not in CONSTRAINT_CHECK_IDS:
            continue
        prefix = CONSTRAINT_FAILURE_PREFIXES.get(check.id)
        if check.id == "parameter_range_check":
            explanation = check.explanation
            if "width must be greater than zero" in explanation:
                prefix = "negative width"
            elif "height must be greater than zero" in explanation:
                prefix = "negative height"
            elif "thickness must be greater than zero" in explanation:
                prefix = "negative thickness"
            elif "hole_diameter must be greater than zero" in explanation:
                prefix = "negative hole diameter"
            elif "corner_radius cannot be negative" in explanation:
                prefix = "corner radius too large"
            elif "edge_fillet_radius cannot be negative" in explanation:
                prefix = "edge fillet radius too large"
            else:
                prefix = "parameter range violation"
        failures.append(f"{prefix or check.id}: {check.explanation}")
    return failures


def _changed_parameter_entry(
    canonical_parameter: str,
    requested_name: str,
    old_value: Any,
    new_value: float,
    reason: str,
) -> dict[str, Any]:
    return {
        "parameter": canonical_parameter,
        "canonical_parameter": canonical_parameter,
        "requested_parameter": requested_name,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
    }


def _parameter_unit(parameter_table: ParameterTable) -> str:
    for name in ("back_plate_width_mm", "back_plate_height_mm", "back_plate_thickness_mm"):
        try:
            unit = parameter_table.get(name).unit
        except KeyError:
            continue
        if unit:
            return unit
    return "mm"


def _numeric_existing_value(parameter_table: ParameterTable, name: str) -> float:
    value = parameter_table.get(name).value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _optional_existing_value(parameter_table: ParameterTable, name: str) -> float | None:
    try:
        return _numeric_existing_value(parameter_table, name)
    except KeyError:
        return None


def _feature_default_parameters(parameter_table: ParameterTable, feature: str, hole_count: int = 2) -> list[Parameter]:
    unit = _parameter_unit(parameter_table)
    width = _numeric_existing_value(parameter_table, "back_plate_width_mm")
    height = _numeric_existing_value(parameter_table, "back_plate_height_mm")

    if feature == "mounting_holes":
        spacing_x = (
            _optional_existing_value(parameter_table, "mounting_hole_spacing_x_mm")
            or _optional_existing_value(parameter_table, "mounting_hole_spacing_mm")
            or width - 40.0
        )
        defaults = [
            Parameter(
                name="mounting_hole_count",
                value=hole_count,
                unit=None,
                description="Number of symmetric mounting holes.",
                source="default",
                reason="Defaulted when mounting holes are explicitly enabled by edit intent.",
                min_value=1.0,
            ),
            Parameter(
                name="mounting_hole_diameter_mm",
                value=5.0,
                unit=unit,
                description="Diameter of each mounting hole.",
                source="default",
                reason="Default clearance-hole diameter used when mounting holes are enabled without a diameter.",
                min_value=1.0,
            ),
            Parameter(
                name="mounting_hole_spacing_x_mm" if hole_count == 4 else "mounting_hole_spacing_mm",
                value=spacing_x,
                unit=unit,
                description=(
                    "Horizontal spacing between rectangular-pattern mounting holes."
                    if hole_count == 4
                    else "Center-to-center spacing between the two symmetric mounting holes."
                ),
                source="derived",
                reason=(
                    "Derived from existing horizontal spacing or width - 40 mm for the four-hole pattern."
                    if hole_count == 4
                    else "Derived as width - 40 mm when mounting holes are enabled without spacing."
                ),
                min_value=1.0,
            ),
        ]
        if hole_count == 4:
            defaults.append(
                Parameter(
                    name="mounting_hole_spacing_y_mm",
                    value=height - 30.0,
                    unit=unit,
                    description="Vertical spacing between rectangular-pattern mounting holes.",
                    source="derived",
                    reason="Derived as height - 30 mm when four mounting holes are enabled without Y spacing.",
                    min_value=1.0,
                )
            )
        return defaults

    if feature == "center_cutout":
        return [
            Parameter(
                name="center_cutout_width_mm",
                value=round(width * 0.35, 3),
                unit=unit,
                description="Width of the centered rectangular cutout.",
                source="derived",
                reason="Derived from plate width when center cutout is enabled without a width.",
                min_value=1.0,
            ),
            Parameter(
                name="center_cutout_height_mm",
                value=round(height * 0.30, 3),
                unit=unit,
                description="Height of the centered rectangular cutout.",
                source="derived",
                reason="Derived from plate height when center cutout is enabled without a height.",
                min_value=1.0,
            ),
        ]

    if feature == "rounded_corners":
        return [
            Parameter(
                name="corner_radius_mm",
                value=4.0,
                unit=unit,
                description="Outside corner radius for the back plate profile.",
                source="default",
                reason="Defaulted when rounded corners are explicitly enabled by edit intent.",
                min_value=0.0,
            )
        ]

    if feature == "edge_fillets":
        return [
            Parameter(
                name="fillet_radius_mm",
                value=1.5,
                unit=unit,
                description="Exposed edge fillet radius.",
                source="default",
                reason="Defaulted when edge fillets are explicitly enabled by edit intent.",
                min_value=0.0,
            )
        ]

    return []


def _merge_parameters(
    parameter_table: ParameterTable,
    updated_values: dict[str, float],
    requested_names: dict[str, str],
    enabled_features: set[str],
    feature_flags: dict[str, dict[str, Any]],
    changed_parameters: list[dict[str, Any]],
) -> list[Parameter]:
    by_name = parameter_table.by_name()
    merged: list[Parameter] = []
    seen: set[str] = set()

    for parameter in parameter_table.parameters:
        if parameter.name in updated_values:
            new_value = updated_values[parameter.name]
            merged.append(parameter.model_copy(update={"value": new_value}))
        else:
            merged.append(parameter)
        seen.add(parameter.name)

    def add_default_parameters(feature: str, hole_count: int = 2) -> None:
        nonlocal merged, seen
        base_for_defaults = parameter_table.model_copy(update={"parameters": merged})
        for default_parameter in _feature_default_parameters(base_for_defaults, feature, hole_count):
            value = updated_values.get(default_parameter.name, default_parameter.value)
            if default_parameter.name in seen:
                continue

            if default_parameter.name in updated_values:
                parameter = default_parameter.model_copy(update={"value": value, "source": "user"})
                requested_name = requested_names.get(default_parameter.name, default_parameter.name)
                reason = "Added because the feature was explicitly enabled and the parameter was edited."
            else:
                parameter = default_parameter
                requested_name = f"enable_feature:{feature}"
                reason = default_parameter.reason

            merged.append(parameter)
            seen.add(parameter.name)
            changed_parameters.append(
                _changed_parameter_entry(
                    default_parameter.name,
                    requested_name,
                    None,
                    float(value),
                    reason,
                )
            )

    for feature in enabled_features:
        add_default_parameters(feature, mounting_hole_count_from_flags(feature_flags) if feature == "mounting_holes" else 2)

    if is_feature_active(feature_flags, "mounting_holes"):
        hole_count = mounting_hole_count_from_flags(feature_flags)
        if hole_count == 4:
            add_default_parameters("mounting_holes", 4)

    for name, value in updated_values.items():
        if name not in seen and name not in by_name:
            raise ValueError(f"cannot add unsupported parameter: {name}")

    return merged


def _preserved_entries(
    original_table: ParameterTable,
    updated_table: ParameterTable,
    changed_names: set[str],
    preserve: list[str],
    constraints: ConstraintGraph | None,
) -> list[dict[str, Any]]:
    preserved: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_entry(name: str, value: Any, reason: str) -> None:
        if name in seen:
            return
        seen.add(name)
        preserved.append({"parameter": name, "preserved_value": value, "reason": reason})

    for requested_name in preserve:
        canonical_name = canonical_parameter_name(requested_name)
        intent_name = canonical_intent_name(requested_name)
        if canonical_name is not None:
            parameter = updated_table.get(canonical_name)
            add_entry(canonical_name, parameter.value, "Explicitly requested preserve entry.")
        elif intent_name == "mounting_hole_symmetry":
            add_entry(
                intent_name,
                _has_symmetry_constraint(constraints),
                "Explicitly requested preserve entry.",
            )
        else:
            add_entry(requested_name, None, "Requested preserve entry is not a known parameter or intent flag.")

    for parameter in original_table.parameters:
        if parameter.name not in changed_names:
            updated_parameter = updated_table.get(parameter.name)
            add_entry(parameter.name, updated_parameter.value, "Unchanged parameter preserved from existing design.")

    return preserved


def _rejected_report(
    parameter_table: ParameterTable,
    changed_parameters: list[dict[str, Any]],
    preserved_parameters: list[dict[str, Any]],
    rejected_edits: list[dict[str, Any]],
    failed_constraints: list[str],
    explanation: str,
) -> EditReport:
    rejected_changes = [
        item.get("reason", str(item)) for item in rejected_edits
    ] + failed_constraints
    return EditReport(
        family=parameter_table.family,
        accepted=False,
        changed_parameters=changed_parameters,
        preserved_parameters=preserved_parameters,
        rejected_edits=rejected_edits,
        failed_constraints=failed_constraints,
        rejected_changes=rejected_changes,
        validation_summary="Edit rejected before geometry regeneration.",
        human_readable_explanation=explanation,
        metadata={"original_parameter_table": parameter_table.model_dump(mode="json")},
    )


def _sync_mounting_hole_feature_flag(
    feature_flags: dict[str, dict[str, Any]],
    parameter_table: ParameterTable,
    updated_values: dict[str, float],
) -> dict[str, dict[str, Any]]:
    synced = normalize_feature_flags(feature_flags)
    if not is_feature_active(synced, "mounting_holes"):
        synced["mounting_holes"] = make_mounting_hole_flag(
            "omitted",
            synced["mounting_holes"]["reason"],
            0,
        )
        return synced

    if "mounting_hole_count" in updated_values:
        hole_count = int(updated_values["mounting_hole_count"])
    else:
        try:
            value = parameter_table.get("mounting_hole_count").value
            hole_count = int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 2
        except KeyError:
            hole_count = mounting_hole_count_from_flags(synced) or 2

    pattern = hole_pattern_for_count(hole_count) or "unsupported"
    synced["mounting_holes"] = make_feature_flag(
        synced["mounting_holes"]["state"],
        synced["mounting_holes"]["reason"],
        feature="mounting_holes",
        hole_count=hole_count,
        pattern=pattern,
    )
    return synced


L_PARAMETER_ALIASES = {
    "base_leg": "base_leg_length_mm",
    "base": "base_leg_length_mm",
    "base_leg_length": "base_leg_length_mm",
    "base_leg_length_mm": "base_leg_length_mm",
    "vertical_leg": "vertical_leg_length_mm",
    "vertical": "vertical_leg_length_mm",
    "upright": "vertical_leg_length_mm",
    "vertical_leg_length": "vertical_leg_length_mm",
    "vertical_leg_length_mm": "vertical_leg_length_mm",
    "bracket_width": "bracket_width_mm",
    "bracket_width_mm": "bracket_width_mm",
    "l_thickness": "thickness_mm",
    "thickness": "thickness_mm",
    "thickness_mm": "thickness_mm",
    "hole_diameter": "hole_diameter_mm",
    "hole_diameter_mm": "hole_diameter_mm",
    "base_hole_count": "base_hole_count",
    "base_hole_spacing": "base_hole_spacing_mm",
    "base_hole_spacing_mm": "base_hole_spacing_mm",
    "vertical_hole_count": "vertical_hole_count",
    "vertical_hole_spacing": "vertical_hole_spacing_mm",
    "vertical_hole_spacing_mm": "vertical_hole_spacing_mm",
    "inside_fillet_radius": "inside_fillet_radius_mm",
    "inside_fillet_radius_mm": "inside_fillet_radius_mm",
    "outside_edge_fillet_radius": "outside_edge_fillet_radius_mm",
    "outside_edge_fillet_radius_mm": "outside_edge_fillet_radius_mm",
    "gusset_thickness": "gusset_thickness_mm",
    "gusset_thickness_mm": "gusset_thickness_mm",
    "gusset_height": "gusset_height_mm",
    "gusset_height_mm": "gusset_height_mm",
}


def _l_canonical_parameter_name(name: str) -> str | None:
    return L_PARAMETER_ALIASES.get(name)


def _l_preserved_entries(
    original_table: ParameterTable,
    updated_table: ParameterTable,
    changed_names: set[str],
    preserve: list[str],
) -> list[dict[str, Any]]:
    preserved: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_entry(name: str, value: Any, reason: str) -> None:
        if name in seen:
            return
        seen.add(name)
        preserved.append({"parameter": name, "preserved_value": value, "reason": reason})

    for requested_name in preserve:
        canonical_name = _l_canonical_parameter_name(requested_name)
        if canonical_name is None:
            add_entry(requested_name, None, "Requested preserve entry is not a known L-bracket parameter.")
            continue
        try:
            parameter = updated_table.get(canonical_name)
        except KeyError:
            add_entry(canonical_name, None, "Requested preserve parameter is not present in the L-bracket table.")
            continue
        add_entry(canonical_name, parameter.value, "Explicitly requested preserve entry.")

    for parameter in original_table.parameters:
        if parameter.name not in changed_names:
            updated_parameter = updated_table.get(parameter.name)
            add_entry(parameter.name, updated_parameter.value, "Unchanged parameter preserved from existing design.")
    return preserved


def _l_unit(parameter_table: ParameterTable) -> str:
    for name in ("base_leg_length_mm", "vertical_leg_length_mm", "bracket_width_mm", "thickness_mm"):
        try:
            unit = parameter_table.get(name).unit
        except KeyError:
            continue
        if unit:
            return unit
    return "mm"


def _l_numeric_from_values(parameter_table: ParameterTable, updated_values: dict[str, float], name: str) -> float:
    if name in updated_values:
        return updated_values[name]
    return _numeric_existing_value(parameter_table, name)


def _l_default_parameters(
    parameter_table: ParameterTable,
    updated_values: dict[str, float],
    feature: str,
) -> list[Parameter]:
    unit = _l_unit(parameter_table)
    base_length = _l_numeric_from_values(parameter_table, updated_values, "base_leg_length_mm")
    vertical_length = _l_numeric_from_values(parameter_table, updated_values, "vertical_leg_length_mm")
    bracket_width = _l_numeric_from_values(parameter_table, updated_values, "bracket_width_mm")
    thickness = _l_numeric_from_values(parameter_table, updated_values, "thickness_mm")
    if feature == "base_mounting_holes":
        return [
            Parameter(name="base_hole_count", value=2, unit=None, description="Number of base-leg mounting holes.", source="default", reason="Defaulted when base mounting holes are enabled.", min_value=0.0),
            Parameter(name="hole_diameter_mm", value=5.0, unit=unit, description="Diameter of L-bracket mounting holes.", source="default", reason="Defaulted when mounting holes are enabled without a diameter.", min_value=1.0),
            Parameter(name="base_hole_spacing_mm", value=base_length - 40.0, unit=unit, description="Spacing between base-leg mounting holes.", source="derived", reason="Derived as base_leg_length - 40 mm when base holes are enabled.", min_value=1.0),
        ]
    if feature == "vertical_mounting_holes":
        return [
            Parameter(name="vertical_hole_count", value=2, unit=None, description="Number of vertical-leg mounting holes.", source="default", reason="Defaulted when vertical mounting holes are enabled.", min_value=0.0),
            Parameter(name="hole_diameter_mm", value=5.0, unit=unit, description="Diameter of L-bracket mounting holes.", source="default", reason="Defaulted when mounting holes are enabled without a diameter.", min_value=1.0),
            Parameter(name="vertical_hole_spacing_mm", value=vertical_length - 40.0, unit=unit, description="Spacing between vertical-leg mounting holes.", source="derived", reason="Derived as vertical_leg_length - 40 mm when vertical holes are enabled.", min_value=1.0),
        ]
    if feature == "triangular_gusset":
        return [
            Parameter(name="gusset_enabled", value=True, unit=None, description="Whether a triangular gusset is active.", source="default", reason="Defaulted when a triangular gusset is enabled."),
            Parameter(name="gusset_thickness_mm", value=min(thickness, bracket_width), unit=unit, description="Triangular gusset thickness across bracket width.", source="derived", reason="Defaulted to bracket thickness when gusset is enabled.", min_value=1.0),
            Parameter(name="gusset_height_mm", value=round(min(base_length, vertical_length) * 0.45, 3), unit=unit, description="Triangular gusset leg height from the inside corner.", source="derived", reason="Defaulted to 45% of the shorter leg when gusset is enabled.", min_value=1.0),
        ]
    if feature == "inside_fillet":
        return [Parameter(name="inside_fillet_radius_mm", value=min(3.0, thickness), unit=unit, description="Inside corner fillet radius.", source="default", reason="Defaulted when inside fillet is enabled.", min_value=0.0)]
    if feature == "outside_edge_fillets":
        return [Parameter(name="outside_edge_fillet_radius_mm", value=min(1.0, thickness / 2), unit=unit, description="Outside edge fillet radius.", source="default", reason="Defaulted when outside edge fillets are enabled.", min_value=0.0)]
    return []


def _apply_l_bracket_edit_request(
    parameter_table: ParameterTable,
    edit_request: dict[str, Any] | EditRequest,
    constraints: ConstraintGraph | None = None,
) -> EditReport:
    edits, preserve = _normalise_edit_request(edit_request)
    if not edits:
        return _rejected_report(
            parameter_table,
            [],
            _l_preserved_entries(parameter_table, parameter_table, set(), preserve),
            [{"reason": "edit request must include at least one edit"}],
            [],
            "Edit rejected because no structured edits were provided.",
        )

    by_name = parameter_table.by_name()
    original_feature_flags = feature_flags_for_parameter_table(parameter_table)
    updated_feature_flags = normalize_feature_flags(original_feature_flags, L_BRACKET_FAMILY)
    enabled_features: set[str] = set()
    disabled_features: set[str] = set()
    feature_flag_changes: list[dict[str, Any]] = []
    changed_parameters: list[dict[str, Any]] = []
    rejected_edits: list[dict[str, Any]] = []
    updated_values: dict[str, float] = {}
    requested_names: dict[str, str] = {}

    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            rejected_edits.append({"edit_index": index, "reason": "edit must be an object"})
            continue
        edit_type = edit.get("type")
        if edit_type in {"enable_feature", "disable_feature"}:
            feature = edit.get("feature")
            if not isinstance(feature, str) or feature not in L_BRACKET_FEATURES:
                rejected_edits.append({"edit_index": index, "edit": edit, "reason": "unsupported L-bracket feature edit"})
                continue
            old_state = updated_feature_flags[feature]["state"]
            reason = edit.get("reason") if isinstance(edit.get("reason"), str) else f"Feature {feature} changed by edit request."
            if edit_type == "enable_feature":
                if feature in {"base_mounting_holes", "vertical_mounting_holes"}:
                    updated_feature_flags[feature] = make_feature_flag("requested_by_user", reason, feature=feature, hole_count=2, pattern="symmetric_2_horizontal")
                else:
                    updated_feature_flags[feature] = make_feature_flag("requested_by_user", reason)
                enabled_features.add(feature)
                new_state = "requested_by_user"
            else:
                if feature in {"base_mounting_holes", "vertical_mounting_holes"}:
                    updated_feature_flags[feature] = make_feature_flag("omitted", reason, feature=feature, hole_count=0, pattern="none")
                    updated_values["base_hole_count" if feature == "base_mounting_holes" else "vertical_hole_count"] = 0.0
                else:
                    updated_feature_flags[feature] = make_feature_flag("omitted", reason)
                    if feature == "triangular_gusset":
                        updated_values["gusset_enabled"] = 0.0
                disabled_features.add(feature)
                new_state = "omitted"
            if old_state != new_state:
                feature_flag_changes.append({"feature": feature, "old_state": old_state, "new_state": new_state, "reason": reason})
            continue

        if edit_type != "set_parameter":
            rejected_edits.append({"edit_index": index, "edit": edit, "reason": "unsupported edit type"})
            continue

        requested_parameter = edit.get("parameter")
        if not isinstance(requested_parameter, str):
            rejected_edits.append({"edit_index": index, "edit": edit, "reason": "set_parameter edit requires a string parameter name"})
            continue
        canonical_parameter = _l_canonical_parameter_name(requested_parameter)
        if canonical_parameter is None:
            rejected_edits.append({"edit_index": index, "parameter": requested_parameter, "reason": f"editing a non-existent parameter is not allowed: {requested_parameter}"})
            continue
        value = edit.get("value")
        if isinstance(value, bool) or not isinstance(value, int | float):
            rejected_edits.append({"edit_index": index, "parameter": requested_parameter, "value": value, "reason": f"editing {requested_parameter} to a non-number value is not allowed"})
            continue
        new_value = float(value)
        if canonical_parameter in {"base_hole_count", "vertical_hole_count"}:
            if int(new_value) not in {0, 2}:
                rejected_edits.append({"edit_index": index, "parameter": requested_parameter, "reason": "L-bracket hole count must be 0 or 2 per leg"})
                continue
            feature = "base_mounting_holes" if canonical_parameter == "base_hole_count" else "vertical_mounting_holes"
            if int(new_value) == 2:
                updated_feature_flags[feature] = make_feature_flag("requested_by_user", f"{feature} enabled by hole-count edit.", feature=feature, hole_count=2, pattern="symmetric_2_horizontal")
                enabled_features.add(feature)
            else:
                updated_feature_flags[feature] = make_feature_flag("omitted", f"{feature} disabled by hole-count edit.", feature=feature, hole_count=0, pattern="none")
                disabled_features.add(feature)
        feature = feature_for_parameter(canonical_parameter)
        if feature in {"base_mounting_holes", "vertical_mounting_holes", "triangular_gusset", "inside_fillet", "outside_edge_fillets"}:
            if not is_feature_active(updated_feature_flags, feature) and feature not in enabled_features and canonical_parameter not in {"base_hole_count", "vertical_hole_count"}:
                rejected_edits.append({"edit_index": index, "parameter": requested_parameter, "canonical_parameter": canonical_parameter, "feature": feature, "reason": f"editing {requested_parameter} is not allowed because {feature} is omitted; enable it first"})
                continue
        if canonical_parameter == "hole_diameter_mm" and not (
            is_feature_active(updated_feature_flags, "base_mounting_holes")
            or is_feature_active(updated_feature_flags, "vertical_mounting_holes")
        ):
            rejected_edits.append({"edit_index": index, "parameter": requested_parameter, "reason": "editing hole diameter is not allowed because L-bracket mounting holes are omitted"})
            continue
        if canonical_parameter not in by_name and feature not in enabled_features:
            rejected_edits.append({"edit_index": index, "parameter": requested_parameter, "canonical_parameter": canonical_parameter, "reason": f"editing a non-existent parameter is not allowed: {requested_parameter}"})
            continue
        updated_values[canonical_parameter] = new_value
        requested_names[canonical_parameter] = requested_parameter
        if canonical_parameter in by_name:
            parameter = by_name[canonical_parameter]
            changed_parameters.append(_changed_parameter_entry(canonical_parameter, requested_parameter, parameter.value, new_value, parameter.reason))

    if rejected_edits:
        return _rejected_report(
            parameter_table,
            [],
            _l_preserved_entries(parameter_table, parameter_table, set(), preserve),
            rejected_edits,
            [],
            "Edit rejected because one or more requested edits were invalid.",
        )

    merged: list[Parameter] = []
    seen: set[str] = set()
    for parameter in parameter_table.parameters:
        if parameter.name in updated_values:
            merged.append(parameter.model_copy(update={"value": updated_values[parameter.name]}))
        else:
            merged.append(parameter)
        seen.add(parameter.name)

    for feature in sorted(enabled_features):
        for default_parameter in _l_default_parameters(parameter_table.model_copy(update={"parameters": merged}), updated_values, feature):
            if default_parameter.name in seen:
                continue
            value = updated_values.get(default_parameter.name, default_parameter.value)
            merged.append(default_parameter.model_copy(update={"value": value}))
            seen.add(default_parameter.name)
            changed_parameters.append(_changed_parameter_entry(default_parameter.name, f"enable_feature:{feature}", None, float(value) if isinstance(value, int | float) and not isinstance(value, bool) else value, default_parameter.reason))

    updated_table = parameter_table.model_copy(update={"parameters": merged})
    metadata = dict(updated_table.metadata)
    metadata["feature_flags"] = normalize_feature_flags(updated_feature_flags, L_BRACKET_FAMILY)
    updated_table = updated_table.model_copy(update={"metadata": metadata})
    changed_names = set(updated_values)
    preserved_parameters = _l_preserved_entries(parameter_table, updated_table, changed_names, preserve)

    try:
        model = build_l_bracket(updated_table)
        validation_report = validate_l_bracket(model, updated_table)
    except Exception as exc:
        return _rejected_report(
            parameter_table,
            changed_parameters,
            preserved_parameters,
            [],
            [f"model regeneration failed: {exc}"],
            "Edit rejected because the updated L-bracket could not be regenerated.",
        )

    if not validation_report.valid:
        return _rejected_report(
            parameter_table,
            changed_parameters,
            preserved_parameters,
            [],
            [check.explanation for check in validation_report.failed_checks],
            "Edit rejected because regenerated L-bracket geometry failed validation.",
        )

    changes_applied = [
        f"{change['parameter']}: {change['old_value']} -> {change['new_value']}"
        for change in changed_parameters
    ]
    changes_applied.extend(
        f"feature {change['feature']}: {change['old_state']} -> {change['new_state']}"
        for change in feature_flag_changes
    )
    return EditReport(
        family=L_BRACKET_FAMILY,
        accepted=True,
        changes_applied=changes_applied,
        updated_parameters=updated_values,
        changed_parameters=changed_parameters,
        preserved_parameters=preserved_parameters,
        validation_report=validation_report,
        validation_summary=validation_report.summary,
        human_readable_explanation=(
            "Edit accepted. Requested L-bracket changes were applied, unchanged parameters were preserved, "
            "the model regenerated successfully, and geometry validation passed."
        ),
        metadata={
            "original_feature_flags": original_feature_flags,
            "updated_feature_flags": updated_feature_flags,
            "feature_flag_changes": feature_flag_changes,
            "disabled_features": sorted(disabled_features),
            "updated_parameter_table": updated_table.model_dump(mode="json"),
        },
    )


def apply_edit_request(
    parameter_table: ParameterTable,
    edit_request: dict[str, Any] | EditRequest,
    constraints: ConstraintGraph | None = None,
) -> EditReport:
    """Apply structured parameter edits while preserving existing design intent."""

    if parameter_table.family == L_BRACKET_FAMILY:
        return _apply_l_bracket_edit_request(parameter_table, edit_request, constraints)

    if parameter_table.family != SUPPORTED_FAMILY:
        raise ValueError(f"unsupported model family: {parameter_table.family}")

    edits, preserve = _normalise_edit_request(edit_request)
    if not edits:
        return _rejected_report(
            parameter_table,
            [],
            _preserved_entries(parameter_table, parameter_table, set(), preserve, constraints),
            [{"reason": "edit request must include at least one edit"}],
            [],
            "Edit rejected because no structured edits were provided.",
        )

    by_name = parameter_table.by_name()
    original_feature_flags = feature_flags_for_parameter_table(parameter_table)
    updated_feature_flags = normalize_feature_flags(original_feature_flags)
    declared_enabled_features = {
        edit["feature"]
        for edit in edits
        if isinstance(edit, dict)
        and edit.get("type") == "enable_feature"
        and isinstance(edit.get("feature"), str)
        and edit["feature"] in OPTIONAL_FEATURES
    }
    declared_disabled_features = {
        edit["feature"]
        for edit in edits
        if isinstance(edit, dict)
        and edit.get("type") == "disable_feature"
        and isinstance(edit.get("feature"), str)
        and edit["feature"] in OPTIONAL_FEATURES
    }
    enabled_features: set[str] = set()
    disabled_features: set[str] = set()
    feature_flag_changes: list[dict[str, Any]] = []
    changed_parameters: list[dict[str, Any]] = []
    rejected_edits: list[dict[str, Any]] = []
    updated_values: dict[str, float] = {}
    requested_names: dict[str, str] = {}

    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            rejected_edits.append({"edit_index": index, "reason": "edit must be an object"})
            continue

        edit_type = edit.get("type")
        if edit_type == "enable_feature":
            feature = edit.get("feature")
            if not isinstance(feature, str) or feature not in OPTIONAL_FEATURES:
                rejected_edits.append(
                    {
                        "edit_index": index,
                        "edit": edit,
                        "reason": f"enable_feature requires one supported feature: {', '.join(OPTIONAL_FEATURES)}",
                    }
                )
                continue

            old_state = updated_feature_flags[feature]["state"]
            reason = (
                edit.get("reason")
                if isinstance(edit.get("reason"), str) and edit.get("reason").strip()
                else f"Feature {feature} was explicitly enabled by edit request."
            )
            updated_feature_flags[feature] = (
                make_mounting_hole_flag("requested_by_user", reason, mounting_hole_count_from_flags(updated_feature_flags) or 2)
                if feature == "mounting_holes"
                else make_feature_flag("requested_by_user", reason)
            )
            enabled_features.add(feature)
            if old_state != "requested_by_user":
                feature_flag_changes.append(
                    {
                        "feature": feature,
                        "old_state": old_state,
                        "new_state": "requested_by_user",
                        "reason": updated_feature_flags[feature]["reason"],
                    }
                )
            continue

        if edit_type == "disable_feature":
            feature = edit.get("feature")
            if not isinstance(feature, str) or feature not in OPTIONAL_FEATURES:
                rejected_edits.append(
                    {
                        "edit_index": index,
                        "edit": edit,
                        "reason": f"disable_feature requires one supported feature: {', '.join(OPTIONAL_FEATURES)}",
                    }
                )
                continue

            old_state = updated_feature_flags[feature]["state"]
            reason = (
                edit.get("reason")
                if isinstance(edit.get("reason"), str) and edit.get("reason").strip()
                else f"Feature {feature} was explicitly disabled by edit request."
            )
            updated_feature_flags[feature] = (
                make_mounting_hole_flag("omitted", reason, 0)
                if feature == "mounting_holes"
                else make_feature_flag("omitted", reason)
            )
            disabled_features.add(feature)
            if old_state != "omitted":
                feature_flag_changes.append(
                    {
                        "feature": feature,
                        "old_state": old_state,
                        "new_state": "omitted",
                        "reason": updated_feature_flags[feature]["reason"],
                    }
                )
            continue

        if edit_type != "set_parameter":
            rejected_edits.append(
                {
                    "edit_index": index,
                    "edit": edit,
                    "reason": (
                        "unsupported edit type; supported types are set_parameter, "
                        "enable_feature, and disable_feature"
                    ),
                }
            )
            continue

        requested_parameter = edit.get("parameter")
        if not isinstance(requested_parameter, str):
            rejected_edits.append(
                {
                    "edit_index": index,
                    "edit": edit,
                    "reason": "set_parameter edit requires a string parameter name",
                }
            )
            continue

        canonical_parameter = canonical_parameter_name(requested_parameter)
        if canonical_parameter is None:
            rejected_edits.append(
                {
                    "edit_index": index,
                    "parameter": requested_parameter,
                    "reason": f"editing a non-existent parameter is not allowed: {requested_parameter}",
                }
            )
            continue

        feature = feature_for_parameter(canonical_parameter)
        if (
            feature is not None
            and feature in declared_disabled_features
            and feature not in declared_enabled_features
        ):
            rejected_edits.append(
                {
                    "edit_index": index,
                    "parameter": requested_parameter,
                    "canonical_parameter": canonical_parameter,
                    "feature": feature,
                    "reason": (
                        f"editing {requested_parameter} is not allowed because {feature} is disabled "
                        "by this edit request"
                    ),
                }
            )
            continue

        if (
            feature is not None
            and not is_feature_active(original_feature_flags, feature)
            and feature not in declared_enabled_features
        ):
            rejected_edits.append(
                {
                    "edit_index": index,
                    "parameter": requested_parameter,
                    "canonical_parameter": canonical_parameter,
                    "feature": feature,
                    "reason": (
                        f"editing {requested_parameter} is not allowed because {feature} is omitted; "
                        f"enable {feature} explicitly before editing its parameters"
                    ),
                }
            )
            continue

        if canonical_parameter not in by_name and feature not in declared_enabled_features:
            rejected_edits.append(
                {
                    "edit_index": index,
                    "parameter": requested_parameter,
                    "canonical_parameter": canonical_parameter,
                    "reason": f"editing a non-existent parameter is not allowed: {requested_parameter}",
                }
            )
            continue

        value = edit.get("value")
        if isinstance(value, bool) or not isinstance(value, int | float):
            rejected_edits.append(
                {
                    "edit_index": index,
                    "parameter": requested_parameter,
                    "value": value,
                    "reason": f"editing {requested_parameter} to a non-number value is not allowed",
                }
            )
            continue

        new_value = float(value)
        updated_values[canonical_parameter] = new_value
        requested_names[canonical_parameter] = requested_parameter
        if canonical_parameter in by_name:
            parameter = by_name[canonical_parameter]
            changed_parameters.append(
                _changed_parameter_entry(
                    canonical_parameter,
                    requested_parameter,
                    parameter.value,
                    new_value,
                    parameter.reason,
                )
            )

    if rejected_edits:
        preserved_parameters = _preserved_entries(parameter_table, parameter_table, set(), preserve, constraints)
        return _rejected_report(
            parameter_table,
            [],
            preserved_parameters,
            rejected_edits,
            [],
            "Edit rejected because one or more requested edits were invalid.",
        )

    updated_feature_flags = _sync_mounting_hole_feature_flag(
        updated_feature_flags,
        parameter_table,
        updated_values,
    )

    try:
        updated_parameters = _merge_parameters(
            parameter_table,
            updated_values,
            requested_names,
            enabled_features,
            updated_feature_flags,
            changed_parameters,
        )
    except (KeyError, ValueError) as exc:
        preserved_parameters = _preserved_entries(parameter_table, parameter_table, set(), preserve, constraints)
        return _rejected_report(
            parameter_table,
            [],
            preserved_parameters,
            [{"reason": str(exc)}],
            [],
            "Edit rejected because feature-enable defaults could not be applied.",
        )

    updated_table = parameter_table.model_copy(update={"parameters": updated_parameters})
    updated_table = _with_feature_flags(updated_table, updated_feature_flags)
    changed_names = set(updated_values)
    preserved_parameters = _preserved_entries(
        parameter_table,
        updated_table,
        changed_names,
        preserve,
        constraints,
    )

    failed_constraints = _constraint_failures(updated_table, constraints)
    if failed_constraints:
        return _rejected_report(
            parameter_table,
            changed_parameters,
            preserved_parameters,
            [],
            failed_constraints,
            "Edit rejected because the updated parameter table violates design constraints.",
        )

    try:
        model = build_wall_bracket(updated_table)
        validation_report = validate_wall_bracket(model, updated_table)
    except Exception as exc:
        return _rejected_report(
            parameter_table,
            changed_parameters,
            preserved_parameters,
            [],
            [f"model regeneration failed: {exc}"],
            "Edit rejected because the updated design could not be regenerated.",
        )

    if not validation_report.valid:
        return _rejected_report(
            parameter_table,
            changed_parameters,
            preserved_parameters,
            [],
            [check.explanation for check in validation_report.failed_checks],
            "Edit rejected because regenerated geometry failed validation.",
        )

    changes_applied = [
        f"{change['parameter']}: {change['old_value']} -> {change['new_value']}"
        for change in changed_parameters
    ]
    changes_applied.extend(
        f"feature {change['feature']}: {change['old_state']} -> {change['new_state']}"
        for change in feature_flag_changes
    )
    explanation = (
        "Edit accepted. Requested parameter changes were applied, unchanged parameters were preserved, "
        "the model regenerated successfully, and geometry validation passed."
    )
    return EditReport(
        family=SUPPORTED_FAMILY,
        accepted=True,
        changes_applied=changes_applied,
        updated_parameters=updated_values,
        changed_parameters=changed_parameters,
        preserved_parameters=preserved_parameters,
        validation_report=validation_report,
        validation_summary=validation_report.summary,
        human_readable_explanation=explanation,
        metadata={
            "original_feature_flags": original_feature_flags,
            "updated_feature_flags": updated_feature_flags,
            "feature_flag_changes": feature_flag_changes,
            "disabled_features": sorted(disabled_features),
            "updated_parameter_table": updated_table.model_dump(mode="json"),
        },
    )


def write_edit_report(report: EditReport, path: str | Path) -> Path:
    """Write an edit report JSON file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
