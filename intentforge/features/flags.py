"""Feature flags for supported bracket model families."""

from __future__ import annotations

from typing import Any

from intentforge.schemas import ParameterTable

WALL_OPTIONAL_FEATURES = (
    "mounting_holes",
    "center_cutout",
    "rounded_corners",
    "edge_fillets",
)

L_BRACKET_FEATURES = (
    "base_leg",
    "vertical_leg",
    "base_mounting_holes",
    "vertical_mounting_holes",
    "inside_fillet",
    "outside_edge_fillets",
    "triangular_gusset",
)

OPTIONAL_FEATURES = WALL_OPTIONAL_FEATURES
OPTIONAL_FEATURES_BY_FAMILY = {
    "wall_mounted_bracket": WALL_OPTIONAL_FEATURES,
    "l_bracket": L_BRACKET_FEATURES,
}
ACTIVE_STATES = {"requested_by_user", "defaulted_by_system"}
OMITTED_STATE = "omitted"
SUPPORTED_HOLE_PATTERNS = {"none", "symmetric_2_horizontal", "rectangular_4"}
HOLE_PATTERN_BY_COUNT = {
    0: "none",
    2: "symmetric_2_horizontal",
    4: "rectangular_4",
}

FEATURE_PARAMETER_MAP: dict[str, str] = {
    "mounting_hole_count": "mounting_holes",
    "mounting_hole_diameter_mm": "mounting_holes",
    "mounting_hole_spacing_mm": "mounting_holes",
    "mounting_hole_spacing_x_mm": "mounting_holes",
    "mounting_hole_spacing_y_mm": "mounting_holes",
    "center_cutout_width_mm": "center_cutout",
    "center_cutout_height_mm": "center_cutout",
    "corner_radius_mm": "rounded_corners",
    "fillet_radius_mm": "edge_fillets",
    "edge_fillet_radius_mm": "edge_fillets",
    "base_hole_count": "base_mounting_holes",
    "base_hole_spacing_mm": "base_mounting_holes",
    "vertical_hole_count": "vertical_mounting_holes",
    "vertical_hole_spacing_mm": "vertical_mounting_holes",
    "inside_fillet_radius_mm": "inside_fillet",
    "outside_edge_fillet_radius_mm": "outside_edge_fillets",
    "gusset_enabled": "triangular_gusset",
    "gusset_thickness_mm": "triangular_gusset",
    "gusset_height_mm": "triangular_gusset",
}


def optional_features_for_family(family: str) -> tuple[str, ...]:
    """Return the feature flag names used by a supported family."""

    return OPTIONAL_FEATURES_BY_FAMILY.get(family, WALL_OPTIONAL_FEATURES)


def hole_pattern_for_count(hole_count: int) -> str | None:
    """Return the supported pattern name for a hole count."""

    return HOLE_PATTERN_BY_COUNT.get(hole_count)


def make_feature_flag(state: str, reason: str, **metadata: Any) -> dict[str, Any]:
    """Create a normalized feature flag entry."""

    if state not in ACTIVE_STATES and state != OMITTED_STATE:
        raise ValueError(f"unsupported feature flag state: {state}")
    return {"state": state, "reason": reason, **metadata}


def make_mounting_hole_flag(state: str, reason: str, hole_count: int = 2) -> dict[str, Any]:
    """Create a mounting-hole feature flag with pattern intent."""

    pattern = hole_pattern_for_count(hole_count)
    if pattern is None:
        pattern = "unsupported"
    return make_feature_flag(
        state,
        reason,
        feature="mounting_holes",
        hole_count=hole_count,
        pattern=pattern,
    )


def normalize_feature_flags(
    raw_flags: dict[str, Any] | None,
    family: str = "wall_mounted_bracket",
) -> dict[str, dict[str, Any]]:
    """Return feature flags with all supported features present."""

    normalized: dict[str, dict[str, Any]] = {}
    raw_flags = raw_flags or {}
    for feature in optional_features_for_family(family):
        raw_flag = raw_flags.get(feature)
        if isinstance(raw_flag, dict):
            state = str(raw_flag.get("state", OMITTED_STATE))
            reason = str(raw_flag.get("reason", "No reason recorded."))
            metadata = {
                key: value
                for key, value in raw_flag.items()
                if key not in {"state", "reason"}
                and isinstance(value, str | int | float | bool)
            }
        else:
            state = OMITTED_STATE
            reason = "Feature omitted."
            metadata = {}
        if feature == "mounting_holes":
            if state in ACTIVE_STATES:
                raw_count = metadata.get("hole_count", 2)
                hole_count = int(raw_count) if isinstance(raw_count, int | float) and not isinstance(raw_count, bool) else 2
                metadata.setdefault("feature", "mounting_holes")
                metadata.setdefault("hole_count", hole_count)
                metadata.setdefault("pattern", hole_pattern_for_count(hole_count) or "unsupported")
            else:
                metadata.setdefault("feature", "mounting_holes")
                metadata.setdefault("hole_count", 0)
                metadata.setdefault("pattern", "none")
        elif feature in {"base_mounting_holes", "vertical_mounting_holes"}:
            metadata.setdefault("feature", feature)
            if state in ACTIVE_STATES:
                raw_count = metadata.get("hole_count", 2)
                hole_count = int(raw_count) if isinstance(raw_count, int | float) and not isinstance(raw_count, bool) else 2
                metadata.setdefault("hole_count", hole_count)
                metadata.setdefault("pattern", "symmetric_2_horizontal" if hole_count == 2 else "unsupported")
            else:
                metadata.setdefault("hole_count", 0)
                metadata.setdefault("pattern", "none")
        normalized[feature] = make_feature_flag(state, reason, **metadata)
    return normalized


def _parameter_names(parameter_table: ParameterTable) -> set[str]:
    return {parameter.name for parameter in parameter_table.parameters}


def _has_positive_parameter(parameter_table: ParameterTable, name: str) -> bool:
    try:
        value = parameter_table.get(name).value
    except KeyError:
        return False
    return isinstance(value, int | float) and not isinstance(value, bool) and value > 0


def _infer_wall_feature_flags(parameter_table: ParameterTable) -> dict[str, dict[str, Any]]:
    names = _parameter_names(parameter_table)
    flags = normalize_feature_flags(None, "wall_mounted_bracket")

    if "mounting_hole_diameter_mm" in names and (
        "mounting_hole_spacing_mm" in names
        or "mounting_hole_spacing_x_mm" in names
    ):
        try:
            raw_count = parameter_table.get("mounting_hole_count").value
            hole_count = int(raw_count) if isinstance(raw_count, int | float) and not isinstance(raw_count, bool) else 2
        except KeyError:
            hole_count = 2
        flags["mounting_holes"] = make_mounting_hole_flag(
            "defaulted_by_system",
            "Inferred from mounting-hole parameters in a legacy parameter table.",
            hole_count,
        )
    if {"center_cutout_width_mm", "center_cutout_height_mm"}.issubset(names):
        flags["center_cutout"] = make_feature_flag(
            "defaulted_by_system",
            "Inferred from center-cutout parameters in a legacy parameter table.",
        )
    if _has_positive_parameter(parameter_table, "corner_radius_mm"):
        flags["rounded_corners"] = make_feature_flag(
            "defaulted_by_system",
            "Inferred from corner-radius parameter in a legacy parameter table.",
        )
    return flags


def _bool_parameter(parameter_table: ParameterTable, name: str) -> bool:
    try:
        value = parameter_table.get(name).value
    except KeyError:
        return False
    return bool(value) if isinstance(value, bool) else False


def _infer_l_bracket_feature_flags(parameter_table: ParameterTable) -> dict[str, dict[str, Any]]:
    names = _parameter_names(parameter_table)
    flags = normalize_feature_flags(None, "l_bracket")
    flags["base_leg"] = make_feature_flag(
        "defaulted_by_system",
        "Base leg is required for the L-bracket family.",
    )
    flags["vertical_leg"] = make_feature_flag(
        "defaulted_by_system",
        "Vertical leg is required for the L-bracket family.",
    )
    if "base_hole_count" in names:
        try:
            raw_count = parameter_table.get("base_hole_count").value
            hole_count = int(raw_count) if isinstance(raw_count, int | float) and not isinstance(raw_count, bool) else 0
        except KeyError:
            hole_count = 0
        if hole_count > 0:
            flags["base_mounting_holes"] = make_feature_flag(
                "defaulted_by_system",
                "Inferred from base-hole parameters in a legacy parameter table.",
                feature="base_mounting_holes",
                hole_count=hole_count,
                pattern="symmetric_2_horizontal" if hole_count == 2 else "unsupported",
            )
    if "vertical_hole_count" in names:
        try:
            raw_count = parameter_table.get("vertical_hole_count").value
            hole_count = int(raw_count) if isinstance(raw_count, int | float) and not isinstance(raw_count, bool) else 0
        except KeyError:
            hole_count = 0
        if hole_count > 0:
            flags["vertical_mounting_holes"] = make_feature_flag(
                "defaulted_by_system",
                "Inferred from vertical-hole parameters in a legacy parameter table.",
                feature="vertical_mounting_holes",
                hole_count=hole_count,
                pattern="symmetric_2_horizontal" if hole_count == 2 else "unsupported",
            )
    if _has_positive_parameter(parameter_table, "inside_fillet_radius_mm"):
        flags["inside_fillet"] = make_feature_flag(
            "defaulted_by_system",
            "Inferred from inside-fillet radius parameter in a legacy parameter table.",
        )
    if _has_positive_parameter(parameter_table, "outside_edge_fillet_radius_mm"):
        flags["outside_edge_fillets"] = make_feature_flag(
            "defaulted_by_system",
            "Inferred from outside-edge fillet radius parameter in a legacy parameter table.",
        )
    if _bool_parameter(parameter_table, "gusset_enabled"):
        flags["triangular_gusset"] = make_feature_flag(
            "defaulted_by_system",
            "Inferred from gusset_enabled parameter in a legacy parameter table.",
        )
    return flags


def _infer_feature_flags(parameter_table: ParameterTable) -> dict[str, dict[str, Any]]:
    if parameter_table.family == "l_bracket":
        return _infer_l_bracket_feature_flags(parameter_table)
    return _infer_wall_feature_flags(parameter_table)


def feature_flags_for_parameter_table(parameter_table: ParameterTable) -> dict[str, dict[str, Any]]:
    """Return explicit feature flags or infer them from legacy parameters."""

    raw_flags = parameter_table.metadata.get("feature_flags")
    if isinstance(raw_flags, dict):
        return normalize_feature_flags(raw_flags, parameter_table.family)
    return _infer_feature_flags(parameter_table)


def is_feature_active(feature_flags: dict[str, Any], feature: str) -> bool:
    """Return True when the feature is requested or system-defaulted."""

    raw_flag = feature_flags.get(feature) if isinstance(feature_flags, dict) else None
    if isinstance(raw_flag, dict):
        return raw_flag.get("state") in ACTIVE_STATES
    return False


def mounting_hole_count_from_flags(feature_flags: dict[str, Any]) -> int:
    """Return the feature-flag mounting-hole count, or zero when omitted."""

    flags = normalize_feature_flags(feature_flags)
    raw_count = flags["mounting_holes"].get("hole_count", 0)
    if isinstance(raw_count, int | float) and not isinstance(raw_count, bool):
        return int(raw_count)
    return 0


def mounting_hole_pattern_from_flags(feature_flags: dict[str, Any]) -> str:
    """Return the normalized mounting-hole pattern name."""

    flags = normalize_feature_flags(feature_flags)
    raw_pattern = flags["mounting_holes"].get("pattern", "none")
    pattern = str(raw_pattern)
    return pattern if pattern in SUPPORTED_HOLE_PATTERNS else "unsupported"


def feature_for_parameter(parameter_name: str) -> str | None:
    """Return the optional feature controlled by a parameter, if any."""

    return FEATURE_PARAMETER_MAP.get(parameter_name)
