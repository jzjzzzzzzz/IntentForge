"""Approximate volume-delta checks for topology-informed validation."""

from __future__ import annotations

from copy import deepcopy
import json
from math import pi
from pathlib import Path
from typing import Any

from harness.topology.shape_inspector import inspect_shape
from intentforge.features import feature_flags_for_parameter_table, is_feature_active, mounting_hole_count_from_flags
from intentforge.generator.cadquery_generator import build_l_bracket, build_wall_bracket
from intentforge.schemas import ParameterTable, ValidationCheck

DEFAULT_TOLERANCE_RATIO = 0.35


def _json_scalar(value: Any) -> int | float | str | bool | None:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    return json.dumps(value, sort_keys=True)


def _numeric_parameter(parameter_table: ParameterTable, *names: str) -> float | None:
    for name in names:
        try:
            value = parameter_table.get(name).value
        except KeyError:
            continue
        if isinstance(value, bool) or not isinstance(value, int | float):
            return None
        return float(value)
    return None


def _int_parameter(parameter_table: ParameterTable, name: str, default: int = 0) -> int:
    try:
        value = parameter_table.get(name).value
    except KeyError:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return int(value)


def _bool_parameter(parameter_table: ParameterTable, name: str, default: bool = False) -> bool:
    try:
        value = parameter_table.get(name).value
    except KeyError:
        return default
    return value if isinstance(value, bool) else default


def estimate_wall_bracket_hole_volume(params: ParameterTable, feature_flags: dict[str, Any] | None = None) -> float:
    """Estimate removed mounting-hole volume for a wall-mounted bracket."""

    flags = feature_flags or feature_flags_for_parameter_table(params)
    if not is_feature_active(flags, "mounting_holes"):
        return 0.0
    count = _int_parameter(params, "mounting_hole_count", mounting_hole_count_from_flags(flags))
    diameter = _numeric_parameter(params, "mounting_hole_diameter_mm")
    thickness = _numeric_parameter(params, "back_plate_thickness_mm")
    if count <= 0 or diameter is None or thickness is None:
        return 0.0
    return count * pi * (diameter / 2) ** 2 * thickness


def estimate_wall_bracket_cutout_volume(params: ParameterTable, feature_flags: dict[str, Any] | None = None) -> float:
    """Estimate removed rectangular center-cutout volume."""

    flags = feature_flags or feature_flags_for_parameter_table(params)
    if not is_feature_active(flags, "center_cutout"):
        return 0.0
    width = _numeric_parameter(params, "center_cutout_width_mm", "cutout_width_mm")
    height = _numeric_parameter(params, "center_cutout_height_mm", "cutout_height_mm")
    thickness = _numeric_parameter(params, "back_plate_thickness_mm")
    if width is None or height is None or thickness is None:
        return 0.0
    return width * height * thickness


def estimate_l_bracket_base_hole_volume(params: ParameterTable, feature_flags: dict[str, Any] | None = None) -> float:
    """Estimate removed base-leg mounting-hole volume for an L-bracket."""

    flags = feature_flags or feature_flags_for_parameter_table(params)
    if not is_feature_active(flags, "base_mounting_holes"):
        return 0.0
    count = _int_parameter(params, "base_hole_count", 0)
    diameter = _numeric_parameter(params, "hole_diameter_mm")
    thickness = _numeric_parameter(params, "thickness_mm")
    if count <= 0 or diameter is None or thickness is None:
        return 0.0
    return count * pi * (diameter / 2) ** 2 * thickness


def estimate_l_bracket_vertical_hole_volume(params: ParameterTable, feature_flags: dict[str, Any] | None = None) -> float:
    """Estimate removed vertical-leg mounting-hole volume for an L-bracket."""

    flags = feature_flags or feature_flags_for_parameter_table(params)
    if not is_feature_active(flags, "vertical_mounting_holes"):
        return 0.0
    count = _int_parameter(params, "vertical_hole_count", 0)
    diameter = _numeric_parameter(params, "hole_diameter_mm")
    thickness = _numeric_parameter(params, "thickness_mm")
    if count <= 0 or diameter is None or thickness is None:
        return 0.0
    return count * pi * (diameter / 2) ** 2 * thickness


def estimate_l_bracket_gusset_volume(params: ParameterTable, feature_flags: dict[str, Any] | None = None) -> float:
    """Estimate added triangular gusset volume for an L-bracket."""

    flags = feature_flags or feature_flags_for_parameter_table(params)
    if not is_feature_active(flags, "triangular_gusset"):
        return 0.0
    if not _bool_parameter(params, "gusset_enabled", True):
        return 0.0
    gusset_thickness = _numeric_parameter(params, "gusset_thickness_mm")
    gusset_height = _numeric_parameter(params, "gusset_height_mm")
    thickness = _numeric_parameter(params, "thickness_mm")
    if gusset_thickness is None or gusset_height is None or thickness is None:
        return 0.0
    leg = max(gusset_height - thickness, 0.0)
    return 0.5 * leg * leg * gusset_thickness


def compare_volume_delta(
    expected_delta: float | None,
    actual_delta: float | None,
    tolerance_ratio: float = DEFAULT_TOLERANCE_RATIO,
) -> dict[str, Any]:
    """Compare signed expected and actual volume deltas with a broad tolerance."""

    if (
        expected_delta is None
        or actual_delta is None
        or isinstance(expected_delta, bool)
        or isinstance(actual_delta, bool)
        or not isinstance(expected_delta, int | float)
        or not isinstance(actual_delta, int | float)
    ):
        return {
            "passed": False,
            "warning": True,
            "tolerance": None,
            "message": "Volume delta comparison could not be performed because a delta is unavailable.",
        }
    if tolerance_ratio < 0:
        return {
            "passed": False,
            "warning": True,
            "tolerance": None,
            "message": "Volume delta comparison could not be performed because tolerance_ratio is negative.",
        }

    expected = float(expected_delta)
    actual = float(actual_delta)
    tolerance = max(abs(expected) * tolerance_ratio, 1e-6)
    direction_ok = (
        abs(expected) <= 1e-9 and abs(actual) <= tolerance
        or expected > 0 and actual > 0
        or expected < 0 and actual < 0
    )
    magnitude_ok = abs(actual - expected) <= tolerance
    passed = direction_ok and magnitude_ok
    if passed:
        message = "Actual volume delta matches expected direction and approximate magnitude."
    elif not direction_ok:
        message = f"Actual volume delta {actual:.6g} has the wrong sign for expected delta {expected:.6g}."
    else:
        message = (
            f"Actual volume delta {actual:.6g} differs from expected delta "
            f"{expected:.6g} by more than tolerance {tolerance:.6g}."
        )
    return {
        "passed": passed,
        "warning": False,
        "tolerance": tolerance,
        "message": message,
    }


def make_volume_delta_check(
    check_id: str,
    description: str,
    expected_delta: float | None,
    actual_delta: float | None,
    *,
    tolerance_ratio: float = DEFAULT_TOLERANCE_RATIO,
    related_features: list[str] | None = None,
    related_parameters: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ValidationCheck:
    """Create a ValidationCheck for an approximate signed volume delta."""

    comparison = compare_volume_delta(expected_delta, actual_delta, tolerance_ratio)
    status = "warning" if comparison["warning"] else ("pass" if comparison["passed"] else "fail")
    return ValidationCheck(
        id=check_id,
        description=description,
        status=status,
        severity="warning" if status == "warning" else "error",
        expected_value=_json_scalar(expected_delta),
        measured_value=_json_scalar(actual_delta),
        tolerance=comparison["tolerance"],
        unit="mm^3",
        related_parameters=related_parameters or [],
        related_features=related_features or [],
        message=comparison["message"],
        metadata={
            "tolerance_ratio": tolerance_ratio,
            **(metadata or {}),
        },
    )


def _with_feature_omitted(parameter_table: ParameterTable, feature: str) -> ParameterTable:
    flags = deepcopy(feature_flags_for_parameter_table(parameter_table))
    current = dict(flags.get(feature, {}))
    current["state"] = "omitted"
    current["reason"] = f"Temporarily omitted {feature} for volume delta baseline."
    if feature == "mounting_holes":
        current["hole_count"] = 0
        current["pattern"] = "none"
    if feature in {"base_mounting_holes", "vertical_mounting_holes"}:
        current["hole_count"] = 0
        current["pattern"] = "none"
    flags[feature] = current
    metadata = {**parameter_table.metadata, "feature_flags": flags}
    return parameter_table.model_copy(update={"metadata": metadata}, deep=True)


def _build_model(parameter_table: ParameterTable) -> Any:
    if parameter_table.family == "l_bracket":
        return build_l_bracket(parameter_table)
    return build_wall_bracket(parameter_table)


def _volume(model: Any, family: str) -> tuple[float | None, list[str]]:
    report = inspect_shape(model, family=family)
    warnings = [f"{warning.metric}: {warning.message}" for warning in report.warnings]
    return report.volume_mm3, warnings


def _volume_delta_record(
    *,
    parameter_table: ParameterTable,
    feature_model: Any,
    omitted_feature: str,
    check_id: str,
    description: str,
    expected_delta: float,
    related_features: list[str],
    related_parameters: list[str],
    tolerance_ratio: float = DEFAULT_TOLERANCE_RATIO,
) -> tuple[ValidationCheck, dict[str, Any]]:
    warnings: list[str] = []
    baseline_volume: float | None = None
    feature_volume: float | None = None
    actual_delta: float | None = None
    try:
        baseline_table = _with_feature_omitted(parameter_table, omitted_feature)
        baseline_model = _build_model(baseline_table)
        baseline_volume, baseline_warnings = _volume(baseline_model, parameter_table.family)
        feature_volume, feature_warnings = _volume(feature_model, parameter_table.family)
        warnings.extend(baseline_warnings)
        warnings.extend(feature_warnings)
        if baseline_volume is not None and feature_volume is not None:
            actual_delta = feature_volume - baseline_volume
    except Exception as exc:  # pragma: no cover - exact CAD/kernel exception types vary
        warnings.append(f"Could not perform baseline comparison for {omitted_feature}: {exc}")

    check = make_volume_delta_check(
        check_id,
        description,
        expected_delta,
        actual_delta,
        tolerance_ratio=tolerance_ratio,
        related_features=related_features,
        related_parameters=related_parameters,
        metadata={
            "baseline_feature_omitted": omitted_feature,
            "baseline_volume_mm3": baseline_volume,
            "feature_volume_mm3": feature_volume,
            "warnings": warnings,
        },
    )
    if warnings and check.status == "pass":
        check = check.model_copy(
            update={
                "status": "warning",
                "severity": "warning",
                "message": f"{check.message} Warnings: {'; '.join(warnings)}",
            }
        )
    record = {
        "id": check.id,
        "feature": omitted_feature,
        "baseline_volume_mm3": baseline_volume,
        "feature_volume_mm3": feature_volume,
        "expected_delta_mm3": expected_delta,
        "actual_delta_mm3": actual_delta,
        "tolerance_mm3": check.tolerance,
        "passed": check.passed,
        "status": check.status,
        "message": check.message,
        "warnings": warnings,
    }
    return check, record


def wall_bracket_volume_delta_checks(
    parameter_table: ParameterTable,
    feature_model: Any,
    *,
    tolerance_ratio: float = DEFAULT_TOLERANCE_RATIO,
) -> tuple[list[ValidationCheck], list[dict[str, Any]]]:
    """Return volume-delta checks for active wall-mounted bracket features."""

    flags = feature_flags_for_parameter_table(parameter_table)
    checks: list[ValidationCheck] = []
    records: list[dict[str, Any]] = []
    if is_feature_active(flags, "mounting_holes"):
        check, record = _volume_delta_record(
            parameter_table=parameter_table,
            feature_model=feature_model,
            omitted_feature="mounting_holes",
            check_id="mounting_hole_volume_delta_check",
            description="Mounting holes reduce model volume by approximately the cylindrical hole volume.",
            expected_delta=-estimate_wall_bracket_hole_volume(parameter_table, flags),
            related_features=["mounting_holes"],
            related_parameters=[
                "mounting_hole_count",
                "mounting_hole_diameter_mm",
                "back_plate_thickness_mm",
            ],
            tolerance_ratio=tolerance_ratio,
        )
        checks.append(check)
        records.append(record)
    if is_feature_active(flags, "center_cutout"):
        check, record = _volume_delta_record(
            parameter_table=parameter_table,
            feature_model=feature_model,
            omitted_feature="center_cutout",
            check_id="center_cutout_volume_delta_check",
            description="Center cutout reduces model volume by approximately the rectangular cutout volume.",
            expected_delta=-estimate_wall_bracket_cutout_volume(parameter_table, flags),
            related_features=["center_cutout"],
            related_parameters=[
                "center_cutout_width_mm",
                "center_cutout_height_mm",
                "back_plate_thickness_mm",
            ],
            tolerance_ratio=tolerance_ratio,
        )
        checks.append(check)
        records.append(record)
    return checks, records


def l_bracket_volume_delta_checks(
    parameter_table: ParameterTable,
    feature_model: Any,
    *,
    tolerance_ratio: float = DEFAULT_TOLERANCE_RATIO,
) -> tuple[list[ValidationCheck], list[dict[str, Any]]]:
    """Return volume-delta checks for active L-bracket features."""

    flags = feature_flags_for_parameter_table(parameter_table)
    checks: list[ValidationCheck] = []
    records: list[dict[str, Any]] = []
    if is_feature_active(flags, "base_mounting_holes"):
        check, record = _volume_delta_record(
            parameter_table=parameter_table,
            feature_model=feature_model,
            omitted_feature="base_mounting_holes",
            check_id="base_hole_volume_delta_check",
            description="Base holes reduce L-bracket volume by approximately the cylindrical hole volume.",
            expected_delta=-estimate_l_bracket_base_hole_volume(parameter_table, flags),
            related_features=["base_mounting_holes"],
            related_parameters=["base_hole_count", "hole_diameter_mm", "thickness_mm"],
            tolerance_ratio=tolerance_ratio,
        )
        checks.append(check)
        records.append(record)
    if is_feature_active(flags, "vertical_mounting_holes"):
        check, record = _volume_delta_record(
            parameter_table=parameter_table,
            feature_model=feature_model,
            omitted_feature="vertical_mounting_holes",
            check_id="vertical_hole_volume_delta_check",
            description="Vertical holes reduce L-bracket volume by approximately the cylindrical hole volume.",
            expected_delta=-estimate_l_bracket_vertical_hole_volume(parameter_table, flags),
            related_features=["vertical_mounting_holes"],
            related_parameters=["vertical_hole_count", "hole_diameter_mm", "thickness_mm"],
            tolerance_ratio=tolerance_ratio,
        )
        checks.append(check)
        records.append(record)
    if is_feature_active(flags, "triangular_gusset"):
        check, record = _volume_delta_record(
            parameter_table=parameter_table,
            feature_model=feature_model,
            omitted_feature="triangular_gusset",
            check_id="gusset_volume_delta_check",
            description="Triangular gusset increases L-bracket volume by approximately its triangular-prism volume.",
            expected_delta=estimate_l_bracket_gusset_volume(parameter_table, flags),
            related_features=["triangular_gusset"],
            related_parameters=["gusset_enabled", "gusset_thickness_mm", "gusset_height_mm"],
            tolerance_ratio=tolerance_ratio,
        )
        checks.append(check)
        records.append(record)
    return checks, records


def volume_delta_checks_for_model(
    parameter_table: ParameterTable,
    feature_model: Any,
    *,
    tolerance_ratio: float = DEFAULT_TOLERANCE_RATIO,
) -> tuple[list[ValidationCheck], list[dict[str, Any]]]:
    """Return volume-delta checks for the supported model family."""

    if parameter_table.family == "l_bracket":
        return l_bracket_volume_delta_checks(parameter_table, feature_model, tolerance_ratio=tolerance_ratio)
    return wall_bracket_volume_delta_checks(parameter_table, feature_model, tolerance_ratio=tolerance_ratio)


def build_volume_delta_report(
    parameter_table: ParameterTable,
    feature_model: Any | None = None,
    *,
    run_id: str | None = None,
    active_features: list[str] | None = None,
    omitted_features: list[str] | None = None,
    output_paths: dict[str, Any] | None = None,
    tolerance_ratio: float = DEFAULT_TOLERANCE_RATIO,
) -> dict[str, Any]:
    """Build a JSON-serializable volume-delta report for a supported model."""

    if feature_model is None:
        feature_model = _build_model(parameter_table)
    feature_volume, shape_warnings = _volume(feature_model, parameter_table.family)
    checks, records = volume_delta_checks_for_model(parameter_table, feature_model, tolerance_ratio=tolerance_ratio)
    warnings = [*shape_warnings]
    for record in records:
        warnings.extend(record.get("warnings", []))
    failed = [record for record in records if record["status"] == "fail"]
    return {
        "run_id": run_id,
        "object_type": parameter_table.family,
        "active_features": active_features or [],
        "omitted_features": omitted_features or [],
        "feature_volume_mm3": feature_volume,
        "checks": records,
        "passed": not failed and all(record["status"] in {"pass", "warning"} for record in records),
        "failed_checks": [record["id"] for record in failed],
        "warnings": warnings,
        "tolerance_ratio": tolerance_ratio,
        "output_paths": output_paths or {},
    }


def write_volume_delta_report(report: dict[str, Any], path: str | Path) -> Path:
    """Write a volume-delta report to JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path
