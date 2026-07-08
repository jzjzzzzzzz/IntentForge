"""Geometry validation for generated wall-mounted bracket models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from intentforge.features import (
    feature_flags_for_parameter_table,
    hole_pattern_for_count,
    is_feature_active,
    mounting_hole_count_from_flags,
    mounting_hole_pattern_from_flags,
)
from intentforge.schemas import ParameterTable, ValidationCheck, ValidationReport

SUPPORTED_FAMILY = "wall_mounted_bracket"
L_BRACKET_FAMILY = "l_bracket"
DEFAULT_MIN_EDGE_DISTANCE_MM = 3.0
BOUNDING_BOX_TOLERANCE_MM = 0.1


PARAMETER_ALIASES = {
    "width": ("back_plate_width_mm",),
    "height": ("back_plate_height_mm",),
    "thickness": ("back_plate_thickness_mm",),
    "hole_count": ("mounting_hole_count",),
    "hole_diameter": ("mounting_hole_diameter_mm",),
    "hole_spacing": ("mounting_hole_spacing_mm",),
    "hole_spacing_x": ("mounting_hole_spacing_x_mm", "mounting_hole_spacing_mm"),
    "hole_spacing_y": ("mounting_hole_spacing_y_mm",),
    "cutout_width": ("center_cutout_width_mm", "cutout_width_mm"),
    "cutout_height": ("center_cutout_height_mm", "cutout_height_mm"),
    "corner_radius": ("corner_radius_mm",),
    "edge_fillet_radius": ("edge_fillet_radius_mm", "fillet_radius_mm"),
    "min_edge_distance": ("min_edge_distance_mm",),
}


def _make_check(
    check_id: str,
    description: str,
    passed: bool,
    expected: Any = None,
    actual: Any = None,
    tolerance: float | None = None,
    severity: str = "error",
    explanation: str = "",
    related_parameters: list[str] | None = None,
    related_features: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ValidationCheck:
    status = "pass" if passed else ("warning" if severity == "warning" else "fail")
    return ValidationCheck(
        id=check_id,
        description=description,
        status=status,
        severity=severity,
        expected_value=_json_scalar(expected),
        measured_value=_json_scalar(actual),
        tolerance=tolerance,
        unit="mm" if tolerance is not None else None,
        related_parameters=related_parameters or [],
        related_features=related_features or [],
        message=explanation,
        metadata=metadata or {},
    )


def _json_scalar(value: Any) -> int | float | str | bool | None:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    return json.dumps(value, sort_keys=True)


def _parameter_value(parameter_table: ParameterTable, aliases: tuple[str, ...]) -> tuple[float | None, str | None]:
    for name in aliases:
        try:
            parameter = parameter_table.get(name)
        except KeyError:
            continue

        value = parameter.value
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None, f"{name} must be numeric"
        return float(value), None

    return None, f"missing required parameter: {' or '.join(aliases)}"


def _read_dimensions(
    parameter_table: ParameterTable,
    feature_flags: dict[str, dict[str, str]],
) -> tuple[dict[str, float | None], dict[str, str]]:
    values: dict[str, float | None] = {}
    errors: dict[str, str] = {}
    active_keys = {"width", "height", "thickness"}
    if is_feature_active(feature_flags, "mounting_holes"):
        active_keys.update({"hole_count", "hole_diameter", "hole_spacing_x"})
        if mounting_hole_pattern_from_flags(feature_flags) == "rectangular_4":
            active_keys.add("hole_spacing_y")
    if is_feature_active(feature_flags, "center_cutout"):
        active_keys.update({"cutout_width", "cutout_height"})
    if is_feature_active(feature_flags, "rounded_corners"):
        active_keys.add("corner_radius")
    if is_feature_active(feature_flags, "edge_fillets"):
        active_keys.add("edge_fillet_radius")

    for key, aliases in PARAMETER_ALIASES.items():
        if key == "min_edge_distance" or key not in active_keys:
            continue
        value, error = _parameter_value(parameter_table, aliases)
        if key == "hole_count" and error:
            values[key] = float(mounting_hole_count_from_flags(feature_flags))
            continue
        values[key] = value
        if error:
            errors[key] = error
    return values, errors


def _min_edge_distance(parameter_table: ParameterTable) -> float:
    value, error = _parameter_value(parameter_table, PARAMETER_ALIASES["min_edge_distance"])
    if error is None and value is not None:
        return value

    metadata_value = parameter_table.metadata.get("min_edge_distance_mm")
    if isinstance(metadata_value, int | float) and not isinstance(metadata_value, bool):
        return float(metadata_value)

    constraints = parameter_table.metadata.get("constraints")
    if isinstance(constraints, dict):
        constraint_value = constraints.get("min_edge_distance_mm")
        if isinstance(constraint_value, int | float) and not isinstance(constraint_value, bool):
            return float(constraint_value)

    return DEFAULT_MIN_EDGE_DISTANCE_MM


def _bbox(model: object) -> tuple[Any | None, str | None]:
    if model is None:
        return None, "model is not available"

    try:
        shape = model.val() if hasattr(model, "val") else model
        return shape.BoundingBox(), None
    except Exception as exc:  # pragma: no cover - exact CadQuery exception type varies
        return None, f"could not read model bounding box: {exc}"


def _is_close(actual: float, expected: float, tolerance: float) -> bool:
    return abs(actual - expected) <= tolerance


def _missing_or_invalid(errors: dict[str, str], *keys: str) -> str | None:
    relevant = [errors[key] for key in keys if key in errors]
    if relevant:
        return "; ".join(relevant)
    return None


def _positive_parameter_check(
    values: dict[str, float | None],
    errors: dict[str, str],
    feature_flags: dict[str, dict[str, str]],
) -> ValidationCheck:
    invalid: list[str] = list(errors.values())
    positive_keys = ["width", "height", "thickness"]
    if is_feature_active(feature_flags, "mounting_holes"):
        positive_keys.extend(["hole_diameter", "hole_spacing_x"])
        if mounting_hole_pattern_from_flags(feature_flags) == "rectangular_4":
            positive_keys.append("hole_spacing_y")
    if is_feature_active(feature_flags, "center_cutout"):
        positive_keys.extend(["cutout_width", "cutout_height"])
    for key in positive_keys:
        value = values.get(key)
        if value is not None and value <= 0:
            invalid.append(f"{key} must be greater than zero")

    if is_feature_active(feature_flags, "rounded_corners"):
        value = values.get("corner_radius")
        if value is not None and value < 0:
            invalid.append("corner_radius cannot be negative")
    if is_feature_active(feature_flags, "edge_fillets"):
        value = values.get("edge_fillet_radius")
        if value is not None and value < 0:
            invalid.append("edge_fillet_radius cannot be negative")

    passed = not invalid
    explanation = "All required parameter ranges are valid." if passed else "; ".join(invalid)
    return _make_check(
        "parameter_range_check",
        "Required bracket parameters are present and inside basic numeric ranges.",
        passed,
        expected="positive dimensions and non-negative radii",
        actual="valid" if passed else explanation,
        explanation=explanation,
        related_parameters=[
            "back_plate_width_mm",
            "back_plate_height_mm",
            "back_plate_thickness_mm",
            "mounting_hole_diameter_mm",
            "mounting_hole_spacing_mm",
            "mounting_hole_spacing_x_mm",
            "mounting_hole_spacing_y_mm",
            "center_cutout_width_mm",
            "center_cutout_height_mm",
            "corner_radius_mm",
            "fillet_radius_mm",
        ],
    )


def _bbox_dimension_check(
    check_id: str,
    description: str,
    axis_length: float | None,
    expected_value: float | None,
    parameter_name: str,
    bbox_error: str | None,
) -> ValidationCheck:
    if expected_value is None:
        return _make_check(
            check_id,
            description,
            False,
            expected="numeric parameter value",
            actual=None,
            tolerance=BOUNDING_BOX_TOLERANCE_MM,
            explanation=f"Cannot check bounding box because {parameter_name} is missing or invalid.",
            related_parameters=[parameter_name],
        )

    if bbox_error:
        return _make_check(
            check_id,
            description,
            False,
            expected=expected_value,
            actual=None,
            tolerance=BOUNDING_BOX_TOLERANCE_MM,
            explanation=bbox_error,
            related_parameters=[parameter_name],
        )

    assert axis_length is not None
    passed = _is_close(axis_length, expected_value, BOUNDING_BOX_TOLERANCE_MM)
    explanation = (
        f"Bounding box length matches {parameter_name}."
        if passed
        else f"Bounding box length {axis_length:.3f} mm does not match {expected_value:.3f} mm."
    )
    return _make_check(
        check_id,
        description,
        passed,
        expected=expected_value,
        actual=axis_length,
        tolerance=BOUNDING_BOX_TOLERANCE_MM,
        explanation=explanation,
        related_parameters=[parameter_name],
    )


def _hole_count(values: dict[str, float | None], feature_flags: dict[str, dict[str, str]]) -> int:
    value = values.get("hole_count")
    if value is not None:
        return int(value)
    return mounting_hole_count_from_flags(feature_flags)


def _hole_pattern_check(values: dict[str, float | None], feature_flags: dict[str, dict[str, str]]) -> ValidationCheck:
    hole_count = _hole_count(values, feature_flags)
    expected_pattern = hole_pattern_for_count(hole_count)
    actual_pattern = mounting_hole_pattern_from_flags(feature_flags)
    passed = expected_pattern is not None and expected_pattern == actual_pattern
    explanation = (
        f"Mounting-hole count {hole_count} matches pattern {actual_pattern}."
        if passed
        else f"Unsupported or mismatched mounting-hole pattern: count {hole_count}, pattern {actual_pattern}."
    )
    return _make_check(
        "hole_pattern_check",
        "Mounting-hole count and pattern are supported and consistent.",
        passed,
        expected="2/symmetric_2_horizontal or 4/rectangular_4",
        actual=f"{hole_count}/{actual_pattern}",
        explanation=explanation,
        related_parameters=["mounting_hole_count"],
        related_features=["mounting_holes"],
    )


def _hole_spacing_range_check(
    values: dict[str, float | None],
    errors: dict[str, str],
    min_edge: float,
    feature_flags: dict[str, dict[str, str]],
) -> ValidationCheck:
    hole_count = _hole_count(values, feature_flags)
    missing_keys = ["width", "hole_diameter", "hole_spacing_x"]
    if hole_count == 4:
        missing_keys.extend(["height", "hole_spacing_y"])
    missing = _missing_or_invalid(errors, *missing_keys)
    if missing:
        return _make_check(
            "hole_spacing_range_check",
            "Mounting-hole pattern fits inside the plate with edge clearance.",
            False,
            expected="hole spacing extents plus hole radius fit within plate limits",
            actual=None,
            explanation=f"Cannot check hole spacing: {missing}",
            related_parameters=[
                "back_plate_width_mm",
                "back_plate_height_mm",
                "mounting_hole_diameter_mm",
                "mounting_hole_spacing_mm",
                "mounting_hole_spacing_x_mm",
                "mounting_hole_spacing_y_mm",
            ],
        )
    if hole_count not in {2, 4}:
        return _make_check(
            "hole_spacing_range_check",
            "Mounting-hole pattern fits inside the plate with edge clearance.",
            False,
            expected="hole_count is 2 or 4",
            actual=hole_count,
            explanation=f"Unsupported mounting-hole count: {hole_count}.",
            related_parameters=["mounting_hole_count"],
        )

    width = values["width"]
    height = values["height"]
    hole_diameter = values["hole_diameter"]
    hole_spacing_x = values["hole_spacing_x"]
    hole_spacing_y = values.get("hole_spacing_y")
    assert width is not None and height is not None and hole_diameter is not None and hole_spacing_x is not None
    actual_x = hole_spacing_x / 2 + hole_diameter / 2
    limit_x = width / 2 - min_edge
    actual_y = None
    limit_y = None
    passed = actual_x <= limit_x
    if hole_count == 4:
        assert hole_spacing_y is not None
        actual_y = hole_spacing_y / 2 + hole_diameter / 2
        limit_y = height / 2 - min_edge
        passed = passed and actual_y <= limit_y
    explanation = (
        f"Hole spacing leaves at least {min_edge:.3f} mm edge clearance."
        if passed
        else (
            f"Hole spacing requires x={actual_x:.3f}"
            + (f", y={actual_y:.3f}" if actual_y is not None else "")
            + f" mm from center but limits are x={limit_x:.3f}"
            + (f", y={limit_y:.3f}" if limit_y is not None else "")
            + " mm."
        )
    )
    return _make_check(
        "hole_spacing_range_check",
        "Mounting-hole pattern fits inside the plate with edge clearance.",
        passed,
        expected=f"x <= {limit_x:.3f}" + (f", y <= {limit_y:.3f}" if limit_y is not None else ""),
        actual=f"x={actual_x:.3f}" + (f", y={actual_y:.3f}" if actual_y is not None else ""),
        explanation=explanation,
        related_parameters=[
            "back_plate_width_mm",
            "back_plate_height_mm",
            "mounting_hole_diameter_mm",
            "mounting_hole_spacing_mm",
            "mounting_hole_spacing_x_mm",
            "mounting_hole_spacing_y_mm",
        ],
        metadata={"min_edge_distance_mm": min_edge, "hole_count": hole_count},
    )


def _hole_diameter_range_check(values: dict[str, float | None], errors: dict[str, str], min_edge: float) -> ValidationCheck:
    missing = _missing_or_invalid(errors, "width", "height", "hole_diameter")
    if missing:
        return _make_check(
            "hole_diameter_range_check",
            "Mounting hole diameter fits inside the plate and leaves material.",
            False,
            expected="hole_diameter < min(width, height)",
            actual=None,
            explanation=f"Cannot check hole diameter: {missing}",
            related_parameters=[
                "back_plate_width_mm",
                "back_plate_height_mm",
                "mounting_hole_diameter_mm",
            ],
        )

    width = values["width"]
    height = values["height"]
    hole_diameter = values["hole_diameter"]
    assert width is not None and height is not None and hole_diameter is not None
    size_limit = min(width, height)
    material_limit = size_limit - 2 * min_edge
    passed = hole_diameter < size_limit and hole_diameter <= material_limit
    explanation = (
        f"Hole diameter leaves at least {min_edge:.3f} mm material at the limiting plate dimension."
        if passed
        else f"Hole diameter {hole_diameter:.3f} mm exceeds material limit {material_limit:.3f} mm."
    )
    return _make_check(
        "hole_diameter_range_check",
        "Mounting hole diameter fits inside the plate and leaves material.",
        passed,
        expected=f"< {size_limit:.3f} and <= {material_limit:.3f}",
        actual=hole_diameter,
        explanation=explanation,
        related_parameters=[
            "back_plate_width_mm",
            "back_plate_height_mm",
            "mounting_hole_diameter_mm",
        ],
        metadata={"min_edge_distance_mm": min_edge},
    )


def _cutout_inside_plate_check(values: dict[str, float | None], errors: dict[str, str], min_edge: float) -> ValidationCheck:
    missing = _missing_or_invalid(errors, "width", "height", "cutout_width", "cutout_height")
    if missing:
        return _make_check(
            "cutout_inside_plate_check",
            "Centered cutout fits inside the plate with edge clearance.",
            False,
            expected="cutout dimensions smaller than plate dimensions minus edge clearances",
            actual=None,
            explanation=f"Cannot check cutout: {missing}",
            related_parameters=[
                "back_plate_width_mm",
                "back_plate_height_mm",
                "center_cutout_width_mm",
                "center_cutout_height_mm",
            ],
        )

    width = values["width"]
    height = values["height"]
    cutout_width = values["cutout_width"]
    cutout_height = values["cutout_height"]
    assert width is not None and height is not None and cutout_width is not None and cutout_height is not None
    width_limit = width - 2 * min_edge
    height_limit = height - 2 * min_edge
    passed = cutout_width < width_limit and cutout_height < height_limit
    explanation = (
        f"Cutout leaves at least {min_edge:.3f} mm edge clearance."
        if passed
        else (
            f"Cutout {cutout_width:.3f} x {cutout_height:.3f} mm exceeds "
            f"limits {width_limit:.3f} x {height_limit:.3f} mm."
        )
    )
    return _make_check(
        "cutout_inside_plate_check",
        "Centered cutout fits inside the plate with edge clearance.",
        passed,
        expected=f"< {width_limit:.3f} x < {height_limit:.3f}",
        actual=f"{cutout_width:.3f} x {cutout_height:.3f}",
        explanation=explanation,
        related_parameters=[
            "back_plate_width_mm",
            "back_plate_height_mm",
            "center_cutout_width_mm",
            "center_cutout_height_mm",
        ],
        metadata={"min_edge_distance_mm": min_edge},
    )


def _corner_radius_limit_check(values: dict[str, float | None], errors: dict[str, str]) -> ValidationCheck:
    missing = _missing_or_invalid(errors, "width", "height", "corner_radius")
    if missing:
        return _make_check(
            "corner_radius_limit_check",
            "Outside corner radius fits within the plate profile.",
            False,
            expected="corner_radius <= min(width, height) / 2",
            actual=None,
            explanation=f"Cannot check corner radius: {missing}",
            related_parameters=["back_plate_width_mm", "back_plate_height_mm", "corner_radius_mm"],
        )

    width = values["width"]
    height = values["height"]
    corner_radius = values["corner_radius"]
    assert width is not None and height is not None and corner_radius is not None
    limit = min(width, height) / 2
    passed = corner_radius <= limit
    explanation = (
        "Corner radius is within the plate profile limit."
        if passed
        else f"Corner radius {corner_radius:.3f} mm exceeds limit {limit:.3f} mm."
    )
    return _make_check(
        "corner_radius_limit_check",
        "Outside corner radius fits within the plate profile.",
        passed,
        expected=f"<= {limit:.3f}",
        actual=corner_radius,
        explanation=explanation,
        related_parameters=["back_plate_width_mm", "back_plate_height_mm", "corner_radius_mm"],
    )


def _edge_fillet_limit_check(values: dict[str, float | None], errors: dict[str, str]) -> ValidationCheck:
    missing = _missing_or_invalid(errors, "thickness", "edge_fillet_radius")
    if missing:
        return _make_check(
            "edge_fillet_limit_check",
            "Edge fillet radius fits within half the plate thickness.",
            False,
            expected="edge_fillet_radius <= thickness / 2",
            actual=None,
            explanation=f"Cannot check edge fillet radius: {missing}",
            related_parameters=["back_plate_thickness_mm", "fillet_radius_mm"],
        )

    thickness = values["thickness"]
    edge_fillet_radius = values["edge_fillet_radius"]
    assert thickness is not None and edge_fillet_radius is not None
    limit = thickness / 2
    passed = edge_fillet_radius <= limit
    explanation = (
        "Edge fillet radius is within the thickness limit."
        if passed
        else f"Edge fillet radius {edge_fillet_radius:.3f} mm exceeds limit {limit:.3f} mm."
    )
    return _make_check(
        "edge_fillet_limit_check",
        "Edge fillet radius fits within half the plate thickness.",
        passed,
        expected=f"<= {limit:.3f}",
        actual=edge_fillet_radius,
        explanation=explanation,
        related_parameters=["back_plate_thickness_mm", "fillet_radius_mm"],
    )


def _normalize_output_paths(output_paths: Any) -> tuple[Path | None, Path | None, str | None]:
    if output_paths is None:
        return None, None, None

    if isinstance(output_paths, dict):
        step_path = output_paths.get("step") or output_paths.get("step_path")
        stl_path = output_paths.get("stl") or output_paths.get("stl_path")
    elif isinstance(output_paths, tuple | list) and len(output_paths) == 2:
        step_path, stl_path = output_paths
    else:
        return None, None, "output_paths must be a dict or a two-item tuple/list"

    if not step_path or not stl_path:
        return None, None, "output_paths must include STEP and STL paths"

    return Path(step_path), Path(stl_path), None


def _export_files_exist_check(output_paths: Any) -> ValidationCheck:
    step_path, stl_path, error = _normalize_output_paths(output_paths)
    if error:
        return _make_check(
            "export_files_exist_check",
            "STEP and STL export files exist and are non-empty.",
            False,
            expected="STEP and STL files exist with size > 0",
            actual=error,
            explanation=error,
        )

    assert step_path is not None and stl_path is not None
    details = {
        "step_path": str(step_path),
        "step_exists": step_path.exists(),
        "step_size": step_path.stat().st_size if step_path.exists() else 0,
        "stl_path": str(stl_path),
        "stl_exists": stl_path.exists(),
        "stl_size": stl_path.stat().st_size if stl_path.exists() else 0,
    }
    passed = bool(
        details["step_exists"]
        and details["stl_exists"]
        and details["step_size"] > 0
        and details["stl_size"] > 0
    )
    explanation = (
        "STEP and STL exports exist and are non-empty."
        if passed
        else "One or more export files are missing or empty."
    )
    return _make_check(
        "export_files_exist_check",
        "STEP and STL export files exist and are non-empty.",
        passed,
        expected="STEP and STL files exist with size > 0",
        actual={
            "step_size": details["step_size"],
            "stl_size": details["stl_size"],
        },
        explanation=explanation,
        metadata=details,
    )


def validate_wall_bracket(
    model: object,
    parameter_table: ParameterTable,
    output_paths: Any = None,
) -> ValidationReport:
    """Validate a generated wall-mounted bracket against named parameters."""

    checks: list[ValidationCheck] = []
    feature_flags = feature_flags_for_parameter_table(parameter_table)
    values, errors = _read_dimensions(parameter_table, feature_flags)
    min_edge = _min_edge_distance(parameter_table)

    family_ok = parameter_table.family == SUPPORTED_FAMILY
    checks.append(
        _make_check(
            "object_family_check",
            "Geometry validation only supports wall_mounted_bracket.",
            family_ok,
            expected=SUPPORTED_FAMILY,
            actual=parameter_table.family,
            explanation=(
                "Parameter table uses the supported bracket family."
                if family_ok
                else f"Unsupported family: {parameter_table.family}"
            ),
        )
    )

    checks.append(_positive_parameter_check(values, errors, feature_flags))

    bbox, bbox_error = _bbox(model)
    checks.extend(
        [
            _bbox_dimension_check(
                "bounding_box_width_check",
                "Bounding box width matches back_plate_width_mm.",
                bbox.xlen if bbox is not None else None,
                values.get("width"),
                "back_plate_width_mm",
                bbox_error,
            ),
            _bbox_dimension_check(
                "bounding_box_height_check",
                "Bounding box height matches back_plate_height_mm.",
                bbox.ylen if bbox is not None else None,
                values.get("height"),
                "back_plate_height_mm",
                bbox_error,
            ),
            _bbox_dimension_check(
                "bounding_box_thickness_check",
                "Bounding box thickness matches back_plate_thickness_mm.",
                bbox.zlen if bbox is not None else None,
                values.get("thickness"),
                "back_plate_thickness_mm",
                bbox_error,
            ),
        ]
    )
    if is_feature_active(feature_flags, "mounting_holes"):
        checks.extend(
            [
                _hole_pattern_check(values, feature_flags),
                _hole_spacing_range_check(values, errors, min_edge, feature_flags),
                _hole_diameter_range_check(values, errors, min_edge),
            ]
        )
    if is_feature_active(feature_flags, "center_cutout"):
        checks.append(_cutout_inside_plate_check(values, errors, min_edge))
    if is_feature_active(feature_flags, "rounded_corners"):
        checks.append(_corner_radius_limit_check(values, errors))
    if is_feature_active(feature_flags, "edge_fillets"):
        checks.append(_edge_fillet_limit_check(values, errors))

    if output_paths is not None:
        checks.append(_export_files_exist_check(output_paths))

    failed_count = sum(1 for check in checks if check.status == "fail")
    warning_count = sum(1 for check in checks if check.status == "warning")
    passed_count = sum(1 for check in checks if check.status in {"pass", "warning"})
    summary = (
        f"Geometry validation completed: {passed_count}/{len(checks)} checks passed, "
        f"{failed_count} failed, {warning_count} warnings."
    )

    return ValidationReport(
        family=SUPPORTED_FAMILY,
        checks=checks,
        summary=summary,
        metadata={
            "validator": "geometry",
            "min_edge_distance_mm": min_edge,
            "feature_flags": feature_flags,
        },
    )


def _exact_numeric(parameter_table: ParameterTable, name: str) -> tuple[float | None, str | None]:
    try:
        parameter = parameter_table.get(name)
    except KeyError:
        return None, f"missing required parameter: {name}"
    value = parameter.value
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None, f"{name} must be numeric"
    return float(value), None


def _exact_bool(parameter_table: ParameterTable, name: str) -> tuple[bool | None, str | None]:
    try:
        parameter = parameter_table.get(name)
    except KeyError:
        return None, f"missing required parameter: {name}"
    if not isinstance(parameter.value, bool):
        return None, f"{name} must be boolean"
    return parameter.value, None


def _l_values(parameter_table: ParameterTable, feature_flags: dict[str, dict[str, Any]]) -> tuple[dict[str, float | bool | None], dict[str, str]]:
    keys = ["base_leg_length", "vertical_leg_length", "bracket_width", "thickness"]
    aliases = {
        "base_leg_length": "base_leg_length_mm",
        "vertical_leg_length": "vertical_leg_length_mm",
        "bracket_width": "bracket_width_mm",
        "thickness": "thickness_mm",
        "hole_diameter": "hole_diameter_mm",
        "base_hole_count": "base_hole_count",
        "base_hole_spacing": "base_hole_spacing_mm",
        "vertical_hole_count": "vertical_hole_count",
        "vertical_hole_spacing": "vertical_hole_spacing_mm",
        "inside_fillet_radius": "inside_fillet_radius_mm",
        "outside_edge_fillet_radius": "outside_edge_fillet_radius_mm",
        "gusset_thickness": "gusset_thickness_mm",
        "gusset_height": "gusset_height_mm",
    }
    if is_feature_active(feature_flags, "base_mounting_holes"):
        keys.extend(["hole_diameter", "base_hole_count", "base_hole_spacing"])
    if is_feature_active(feature_flags, "vertical_mounting_holes"):
        keys.extend(["hole_diameter", "vertical_hole_count", "vertical_hole_spacing"])
    if is_feature_active(feature_flags, "inside_fillet"):
        keys.append("inside_fillet_radius")
    if is_feature_active(feature_flags, "outside_edge_fillets"):
        keys.append("outside_edge_fillet_radius")
    if is_feature_active(feature_flags, "triangular_gusset"):
        keys.extend(["gusset_thickness", "gusset_height"])

    values: dict[str, float | bool | None] = {}
    errors: dict[str, str] = {}
    for key in dict.fromkeys(keys):
        value, error = _exact_numeric(parameter_table, aliases[key])
        values[key] = value
        if error:
            errors[key] = error
    if is_feature_active(feature_flags, "triangular_gusset"):
        value, error = _exact_bool(parameter_table, "gusset_enabled")
        values["gusset_enabled"] = value
        if error:
            errors["gusset_enabled"] = error
    return values, errors


def _l_parameter_range_check(values: dict[str, float | bool | None], errors: dict[str, str], feature_flags: dict[str, dict[str, Any]]) -> ValidationCheck:
    invalid = list(errors.values())
    positive_keys = ["base_leg_length", "vertical_leg_length", "bracket_width", "thickness"]
    if is_feature_active(feature_flags, "base_mounting_holes"):
        positive_keys.extend(["hole_diameter", "base_hole_spacing"])
    if is_feature_active(feature_flags, "vertical_mounting_holes"):
        positive_keys.extend(["hole_diameter", "vertical_hole_spacing"])
    if is_feature_active(feature_flags, "triangular_gusset"):
        positive_keys.extend(["gusset_thickness", "gusset_height"])
    for key in dict.fromkeys(positive_keys):
        value = values.get(key)
        if isinstance(value, int | float) and value <= 0:
            invalid.append(f"{key} must be greater than zero")
    for key in ["inside_fillet_radius", "outside_edge_fillet_radius"]:
        value = values.get(key)
        if isinstance(value, int | float) and value < 0:
            invalid.append(f"{key} cannot be negative")
    passed = not invalid
    return _make_check(
        "l_parameter_range_check",
        "Required L-bracket parameters are present and inside basic numeric ranges.",
        passed,
        expected="positive dimensions and non-negative radii",
        actual="valid" if passed else "; ".join(invalid),
        explanation="All required L-bracket parameter ranges are valid." if passed else "; ".join(invalid),
    )


def _l_hole_count_check(values: dict[str, float | bool | None], feature: str) -> ValidationCheck:
    key = "base_hole_count" if feature == "base_mounting_holes" else "vertical_hole_count"
    value = values.get(key)
    hole_count = int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None
    passed = hole_count in {0, 2}
    return _make_check(
        f"{key}_check",
        f"{key} is supported by Phase 10.",
        passed,
        expected="0 or 2",
        actual=hole_count,
        explanation=(
            f"{key} is supported."
            if passed
            else f"Unsupported {key}: {hole_count}. Phase 10 supports only 0 or 2 holes per leg."
        ),
        related_parameters=[key],
        related_features=[feature],
    )


def _l_hole_fit_check(
    values: dict[str, float | bool | None],
    min_edge: float,
    *,
    leg: str,
) -> ValidationCheck:
    length_key = "base_leg_length" if leg == "base" else "vertical_leg_length"
    spacing_key = "base_hole_spacing" if leg == "base" else "vertical_hole_spacing"
    count_key = "base_hole_count" if leg == "base" else "vertical_hole_count"
    feature = "base_mounting_holes" if leg == "base" else "vertical_mounting_holes"
    length = values.get(length_key)
    spacing = values.get(spacing_key)
    diameter = values.get("hole_diameter")
    count = values.get(count_key)
    if not all(isinstance(value, int | float) and not isinstance(value, bool) for value in (length, spacing, diameter, count)):
        return _make_check(
            f"{leg}_hole_spacing_range_check",
            f"{leg.title()} holes fit inside the L-bracket leg with edge clearance.",
            False,
            expected="numeric hole spacing, diameter, and leg length",
            actual=None,
            explanation=f"Cannot check {leg} holes because required numeric parameters are missing or invalid.",
            related_features=[feature],
        )
    if int(count) == 0:
        return _make_check(
            f"{leg}_hole_spacing_range_check",
            f"{leg.title()} holes fit inside the L-bracket leg with edge clearance.",
            True,
            expected="no active holes",
            actual="no active holes",
            explanation=f"No {leg} holes are active.",
            related_features=[feature],
        )
    actual = float(spacing) / 2 + float(diameter) / 2
    limit = float(length) / 2 - min_edge
    passed = actual <= limit
    return _make_check(
        f"{leg}_hole_spacing_range_check",
        f"{leg.title()} holes fit inside the L-bracket leg with edge clearance.",
        passed,
        expected=f"<= {limit:.3f}",
        actual=f"{actual:.3f}",
        explanation=(
            f"{leg.title()} hole spacing leaves at least {min_edge:.3f} mm edge clearance."
            if passed
            else f"{leg.title()} hole spacing requires {actual:.3f} mm from center but limit is {limit:.3f} mm."
        ),
        related_features=[feature],
        metadata={"min_edge_distance_mm": min_edge},
    )


def _l_hole_diameter_check(values: dict[str, float | bool | None], min_edge: float) -> ValidationCheck:
    diameter = values.get("hole_diameter")
    width = values.get("bracket_width")
    if not isinstance(diameter, int | float) or isinstance(diameter, bool):
        return _make_check(
            "l_hole_diameter_range_check",
            "L-bracket hole diameter leaves material across bracket width.",
            False,
            expected="numeric hole_diameter_mm",
            actual=None,
            explanation="Cannot check L-bracket hole diameter because hole_diameter_mm is missing or invalid.",
        )
    if not isinstance(width, int | float) or isinstance(width, bool):
        return _make_check(
            "l_hole_diameter_range_check",
            "L-bracket hole diameter leaves material across bracket width.",
            False,
            expected="numeric bracket_width_mm",
            actual=None,
            explanation="Cannot check L-bracket hole diameter because bracket_width_mm is missing or invalid.",
        )
    material_limit = float(width) - 2 * min_edge
    passed = float(diameter) <= material_limit
    return _make_check(
        "l_hole_diameter_range_check",
        "L-bracket hole diameter leaves material across bracket width.",
        passed,
        expected=f"<= {material_limit:.3f}",
        actual=float(diameter),
        explanation=(
            "Hole diameter leaves material across the bracket width."
            if passed
            else f"Hole diameter {float(diameter):.3f} mm exceeds width material limit {material_limit:.3f} mm."
        ),
        metadata={"min_edge_distance_mm": min_edge},
    )


def _l_fillet_check(values: dict[str, float | bool | None], key: str, limit: float | None) -> ValidationCheck:
    value = values.get(key)
    passed = isinstance(value, int | float) and not isinstance(value, bool) and limit is not None and float(value) <= limit
    return _make_check(
        f"{key}_limit_check",
        f"{key} fits within L-bracket thickness limits.",
        passed,
        expected=f"<= {limit:.3f}" if limit is not None else "valid thickness",
        actual=float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None,
        explanation=(
            f"{key} is within the allowed limit."
            if passed
            else f"{key} is missing, invalid, or exceeds the allowed limit."
        ),
        related_parameters=[f"{key}_mm"],
    )


def _l_gusset_check(values: dict[str, float | bool | None]) -> ValidationCheck:
    enabled = values.get("gusset_enabled")
    thickness = values.get("gusset_thickness")
    height = values.get("gusset_height")
    width = values.get("bracket_width")
    base = values.get("base_leg_length")
    vertical = values.get("vertical_leg_length")
    numeric = all(isinstance(value, int | float) and not isinstance(value, bool) for value in (thickness, height, width, base, vertical))
    passed = bool(enabled) and numeric and float(thickness) <= float(width) and float(height) < min(float(base), float(vertical))
    return _make_check(
        "gusset_dimensions_check",
        "Triangular gusset dimensions fit inside the L-bracket corner.",
        passed,
        expected="enabled gusset with thickness <= bracket_width and height < shorter leg",
        actual={
            "enabled": enabled,
            "gusset_thickness": thickness,
            "gusset_height": height,
        },
        explanation=(
            "Triangular gusset dimensions are valid."
            if passed
            else "Triangular gusset is disabled, missing dimensions, or too large for the L-bracket."
        ),
        related_features=["triangular_gusset"],
    )


def validate_l_bracket(
    model: object,
    parameter_table: ParameterTable,
    output_paths: Any = None,
) -> ValidationReport:
    """Validate a generated L-bracket against named parameters."""

    checks: list[ValidationCheck] = []
    feature_flags = feature_flags_for_parameter_table(parameter_table)
    values, errors = _l_values(parameter_table, feature_flags)
    min_edge = _min_edge_distance(parameter_table)

    family_ok = parameter_table.family == L_BRACKET_FAMILY
    checks.append(
        _make_check(
            "object_family_check",
            "Geometry validation supports l_bracket.",
            family_ok,
            expected=L_BRACKET_FAMILY,
            actual=parameter_table.family,
            explanation="Parameter table uses the L-bracket family." if family_ok else f"Unsupported family: {parameter_table.family}",
        )
    )
    checks.append(_l_parameter_range_check(values, errors, feature_flags))

    bbox, bbox_error = _bbox(model)
    checks.extend(
        [
            _bbox_dimension_check(
                "bounding_box_base_leg_length_check",
                "Bounding box X length matches base_leg_length_mm.",
                bbox.xlen if bbox is not None else None,
                values.get("base_leg_length") if isinstance(values.get("base_leg_length"), int | float) else None,
                "base_leg_length_mm",
                bbox_error,
            ),
            _bbox_dimension_check(
                "bounding_box_bracket_width_check",
                "Bounding box Y length matches bracket_width_mm.",
                bbox.ylen if bbox is not None else None,
                values.get("bracket_width") if isinstance(values.get("bracket_width"), int | float) else None,
                "bracket_width_mm",
                bbox_error,
            ),
            _bbox_dimension_check(
                "bounding_box_vertical_leg_length_check",
                "Bounding box Z length matches vertical_leg_length_mm.",
                bbox.zlen if bbox is not None else None,
                values.get("vertical_leg_length") if isinstance(values.get("vertical_leg_length"), int | float) else None,
                "vertical_leg_length_mm",
                bbox_error,
            ),
        ]
    )
    if is_feature_active(feature_flags, "base_mounting_holes"):
        checks.append(_l_hole_count_check(values, "base_mounting_holes"))
        checks.append(_l_hole_fit_check(values, min_edge, leg="base"))
    if is_feature_active(feature_flags, "vertical_mounting_holes"):
        checks.append(_l_hole_count_check(values, "vertical_mounting_holes"))
        checks.append(_l_hole_fit_check(values, min_edge, leg="vertical"))
    if is_feature_active(feature_flags, "base_mounting_holes") or is_feature_active(feature_flags, "vertical_mounting_holes"):
        checks.append(_l_hole_diameter_check(values, min_edge))
    thickness = values.get("thickness")
    thickness_value = float(thickness) if isinstance(thickness, int | float) and not isinstance(thickness, bool) else None
    if is_feature_active(feature_flags, "inside_fillet"):
        checks.append(_l_fillet_check(values, "inside_fillet_radius", thickness_value))
    if is_feature_active(feature_flags, "outside_edge_fillets"):
        checks.append(_l_fillet_check(values, "outside_edge_fillet_radius", thickness_value / 2 if thickness_value is not None else None))
    if is_feature_active(feature_flags, "triangular_gusset"):
        checks.append(_l_gusset_check(values))
    if output_paths is not None:
        checks.append(_export_files_exist_check(output_paths))

    failed_count = sum(1 for check in checks if check.status == "fail")
    warning_count = sum(1 for check in checks if check.status == "warning")
    passed_count = sum(1 for check in checks if check.status in {"pass", "warning"})
    summary = (
        f"L-bracket geometry validation completed: {passed_count}/{len(checks)} checks passed, "
        f"{failed_count} failed, {warning_count} warnings."
    )
    return ValidationReport(
        family=L_BRACKET_FAMILY,
        checks=checks,
        summary=summary,
        metadata={
            "validator": "geometry",
            "min_edge_distance_mm": min_edge,
            "feature_flags": feature_flags,
        },
    )


def write_validation_report(report: ValidationReport, path: str | Path) -> Path:
    """Write a validation report JSON file with computed summary fields."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def validate_geometry(model: object, parameters: ParameterTable) -> ValidationReport:
    """Backward-compatible geometry validation wrapper."""

    if parameters.family == L_BRACKET_FAMILY:
        return validate_l_bracket(model, parameters)
    return validate_wall_bracket(model, parameters)
