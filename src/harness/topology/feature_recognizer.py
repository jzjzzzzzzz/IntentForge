"""Topology-informed feature recognition for supported IntentForge models."""

from __future__ import annotations

from collections.abc import Iterable
import json
from pathlib import Path
from typing import Any

from harness.reports import FeatureRecognitionReport
from harness.topology.shape_inspector import inspect_shape
from intentforge.features import feature_flags_for_parameter_table, is_feature_active
from intentforge.schemas import ParameterTable

SUPPORTED_FAMILIES = {"wall_mounted_bracket", "l_bracket"}
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_UNKNOWN = "unknown"


def _shape_from_model(shape_or_model: Any) -> tuple[Any | None, list[str]]:
    if shape_or_model is None:
        return None, ["No CadQuery model or shape was provided."]
    if hasattr(shape_or_model, "val") and callable(shape_or_model.val):
        try:
            return shape_or_model.val(), []
        except Exception as exc:  # pragma: no cover - kernel exceptions vary
            return None, [f"Could not extract CadQuery shape with val(): {exc}"]
    return shape_or_model, []


def _collection(shape: Any, method_name: str) -> tuple[list[Any], str | None]:
    if shape is None:
        return [], "No shape was available."
    method = getattr(shape, method_name, None)
    if not callable(method):
        return [], f"Shape does not expose {method_name}()."
    try:
        values = method()
    except Exception as exc:  # pragma: no cover - kernel exceptions vary
        return [], f"{method_name}() failed: {exc}"
    try:
        return list(values), None
    except TypeError:
        return [], f"{method_name}() did not return an iterable collection."


def _geom_type(topology_object: Any) -> str:
    method = getattr(topology_object, "geomType", None)
    if callable(method):
        try:
            return str(method())
        except Exception:  # pragma: no cover - backend-specific
            return "UNKNOWN"
    return "UNKNOWN"


def _bbox(topology_object: Any) -> dict[str, float] | None:
    method = getattr(topology_object, "BoundingBox", None)
    if not callable(method):
        return None
    try:
        box = method()
    except Exception:  # pragma: no cover - backend-specific
        return None
    fields = {
        "xmin": getattr(box, "xmin", None),
        "ymin": getattr(box, "ymin", None),
        "zmin": getattr(box, "zmin", None),
        "xmax": getattr(box, "xmax", None),
        "ymax": getattr(box, "ymax", None),
        "zmax": getattr(box, "zmax", None),
        "xlen": getattr(box, "xlen", None),
        "ylen": getattr(box, "ylen", None),
        "zlen": getattr(box, "zlen", None),
    }
    if any(isinstance(value, bool) or not isinstance(value, int | float) for value in fields.values()):
        return None
    result = {key: float(value) for key, value in fields.items()}
    result["cx"] = (result["xmin"] + result["xmax"]) / 2
    result["cy"] = (result["ymin"] + result["ymax"]) / 2
    result["cz"] = (result["zmin"] + result["zmax"]) / 2
    return result


def _numeric_parameter(parameter_table: ParameterTable, *names: str) -> float | None:
    for name in names:
        try:
            value = parameter_table.get(name).value
        except KeyError:
            continue
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None


def _integer_parameter(parameter_table: ParameterTable, name: str, default: int = 0) -> int:
    value = _numeric_parameter(parameter_table, name)
    return int(value) if value is not None else default


def _boolean_parameter(parameter_table: ParameterTable, name: str, default: bool = False) -> bool:
    try:
        value = parameter_table.get(name).value
    except KeyError:
        return default
    return value if isinstance(value, bool) else default


def _axis_extent(box: dict[str, float], axis: str) -> float:
    return box[f"{axis}len"]


def _cross_extents(box: dict[str, float], axis: str) -> tuple[float, float]:
    axes = [candidate for candidate in ("x", "y", "z") if candidate != axis]
    return box[f"{axes[0]}len"], box[f"{axes[1]}len"]


def _center_for_axes(box: dict[str, float], axes: Iterable[str]) -> tuple[float, ...]:
    return tuple(box[f"c{axis}"] for axis in axes)


def _candidate_radius(edge_or_face: Any, box: dict[str, float] | None = None, axis: str | None = None) -> float | None:
    radius = getattr(edge_or_face, "radius", None)
    if callable(radius):
        try:
            value = radius()
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
        except Exception:  # pragma: no cover - backend-specific
            pass
    if box and axis:
        cross_a, cross_b = _cross_extents(box, axis)
        return (cross_a + cross_b) / 4
    return None


def _cylindrical_candidates(shape: Any, expected_axis: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    faces, warning = _collection(shape, "Faces")
    warnings = [warning] if warning else []
    candidates: list[dict[str, Any]] = []
    for index, face in enumerate(faces):
        if _geom_type(face) != "CYLINDER":
            continue
        box = _bbox(face)
        if not box:
            warnings.append(f"Cylindrical face {index} did not expose a readable bounding box.")
            continue
        axes = ("x", "y", "z")
        possible_axes = [axis for axis in axes if _axis_extent(box, axis) > 0]
        if expected_axis:
            possible_axes = [axis for axis in possible_axes if axis == expected_axis]
        if not possible_axes:
            continue
        axis = expected_axis or max(possible_axes, key=lambda item: _axis_extent(box, item))
        candidates.append(
            {
                "index": index,
                "axis": axis,
                "center": {"x": box["cx"], "y": box["cy"], "z": box["cz"]},
                "bbox": box,
                "radius_estimate_mm": _candidate_radius(face, box, axis),
                "area_mm2": _safe_area(face),
            }
        )
    return candidates, warnings


def _safe_area(face: Any) -> float | None:
    method = getattr(face, "Area", None)
    if not callable(method):
        return None
    try:
        value = method()
    except Exception:  # pragma: no cover - backend-specific
        return None
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _close(value: float, expected: float, tolerance: float) -> bool:
    return abs(value - expected) <= tolerance


def _feature_result(
    *,
    expected: Any = None,
    recognized: Any = None,
    expected_count: int | None = None,
    recognized_count: int | None = None,
    passed: bool = True,
    confidence: str = CONFIDENCE_MEDIUM,
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "passed": passed,
        "confidence": confidence,
        "warnings": warnings or [],
    }
    if expected is not None:
        result["expected"] = expected
    if recognized is not None:
        result["recognized"] = recognized
    if expected_count is not None:
        result["expected_count"] = expected_count
    if recognized_count is not None:
        result["recognized_count"] = recognized_count
    if metadata:
        result["metadata"] = metadata
    return result


def recognize_through_holes(
    shape: Any,
    expected_axis: str | None = None,
    *,
    expected_count: int | None = None,
    expected_diameter_mm: float | None = None,
    expected_centers: list[tuple[float, float]] | None = None,
    center_axes: tuple[str, str] = ("x", "y"),
    through_length_mm: float | None = None,
    tolerance_mm: float | None = None,
) -> dict[str, Any]:
    """Recognize through-hole candidates from cylindrical faces.

    This is intentionally parameter-aware. It matches expected hole centers
    where available, which avoids mistaking rounded outside corners for holes.
    """

    shape, extraction_warnings = _shape_from_model(shape)
    if shape is None:
        return _feature_result(
            expected_count=expected_count,
            recognized_count=0,
            passed=False,
            confidence=CONFIDENCE_UNKNOWN,
            warnings=extraction_warnings,
        )

    candidates, warnings = _cylindrical_candidates(shape, expected_axis)
    warnings.extend(extraction_warnings)
    tolerance = tolerance_mm or max((expected_diameter_mm or 0) * 0.75, 1.0)
    diameter_tolerance = max((expected_diameter_mm or 0) * 0.35, 0.75)
    length_tolerance = max((through_length_mm or 0) * 0.35, 0.75)

    matched: list[dict[str, Any]] = []
    for candidate in candidates:
        if expected_diameter_mm is not None and candidate.get("radius_estimate_mm") is not None:
            diameter = 2 * float(candidate["radius_estimate_mm"])
            if not _close(diameter, expected_diameter_mm, diameter_tolerance):
                continue
        if expected_axis and through_length_mm is not None:
            extent = _axis_extent(candidate["bbox"], expected_axis)
            if not _close(extent, through_length_mm, length_tolerance):
                continue
        if expected_centers:
            center = _center_for_axes(candidate["bbox"], center_axes)
            if not any(
                _close(center[0], expected[0], tolerance) and _close(center[1], expected[1], tolerance)
                for expected in expected_centers
            ):
                continue
        matched.append(candidate)

    recognized_count = len(matched)
    passed = expected_count is None or recognized_count == expected_count
    confidence = CONFIDENCE_MEDIUM if passed else CONFIDENCE_LOW
    if expected_centers and expected_count is not None and passed:
        confidence = CONFIDENCE_HIGH
    if expected_count is not None and not passed:
        warnings.append(
            f"Expected {expected_count} through-hole candidates but recognized {recognized_count}."
        )

    return _feature_result(
        expected_count=expected_count,
        recognized_count=recognized_count,
        passed=passed,
        confidence=confidence,
        warnings=warnings,
        metadata={
            "expected_axis": expected_axis,
            "expected_diameter_mm": expected_diameter_mm,
            "through_length_mm": through_length_mm,
            "candidate_count": len(candidates),
            "matched_candidates": matched,
        },
    )


def _wall_expected_hole_centers(parameter_table: ParameterTable) -> list[tuple[float, float]]:
    flags = feature_flags_for_parameter_table(parameter_table)
    count = _integer_parameter(parameter_table, "mounting_hole_count", 0)
    spacing_x = _numeric_parameter(parameter_table, "mounting_hole_spacing_x_mm", "mounting_hole_spacing_mm")
    spacing_y = _numeric_parameter(parameter_table, "mounting_hole_spacing_y_mm")
    if not is_feature_active(flags, "mounting_holes") or spacing_x is None:
        return []
    if count == 4 and spacing_y is not None:
        return [
            (-spacing_x / 2, -spacing_y / 2),
            (spacing_x / 2, -spacing_y / 2),
            (-spacing_x / 2, spacing_y / 2),
            (spacing_x / 2, spacing_y / 2),
        ]
    if count == 2:
        return [(-spacing_x / 2, 0.0), (spacing_x / 2, 0.0)]
    return []


def _l_base_expected_hole_centers(parameter_table: ParameterTable) -> list[tuple[float, float]]:
    count = _integer_parameter(parameter_table, "base_hole_count", 0)
    spacing = _numeric_parameter(parameter_table, "base_hole_spacing_mm")
    base_length = _numeric_parameter(parameter_table, "base_leg_length_mm")
    if count != 2 or spacing is None or base_length is None:
        return []
    return [(base_length / 2 - spacing / 2, 0.0), (base_length / 2 + spacing / 2, 0.0)]


def _l_vertical_expected_hole_centers(parameter_table: ParameterTable) -> list[tuple[float, float]]:
    count = _integer_parameter(parameter_table, "vertical_hole_count", 0)
    spacing = _numeric_parameter(parameter_table, "vertical_hole_spacing_mm")
    vertical_length = _numeric_parameter(parameter_table, "vertical_leg_length_mm")
    if count != 2 or spacing is None or vertical_length is None:
        return []
    return [(0.0, vertical_length / 2 - spacing / 2), (0.0, vertical_length / 2 + spacing / 2)]


def recognize_center_cutout(shape: Any, parameter_table: ParameterTable) -> dict[str, Any]:
    """Recognize a centered rectangular through cutout using internal planar walls."""

    flags = feature_flags_for_parameter_table(parameter_table)
    expected = is_feature_active(flags, "center_cutout")
    if not expected:
        return _feature_result(expected=False, recognized=False, passed=True, confidence=CONFIDENCE_HIGH)

    shape, extraction_warnings = _shape_from_model(shape)
    if shape is None:
        return _feature_result(
            expected=True,
            recognized=False,
            passed=False,
            confidence=CONFIDENCE_UNKNOWN,
            warnings=extraction_warnings,
        )

    cutout_width = _numeric_parameter(parameter_table, "center_cutout_width_mm", "cutout_width_mm")
    cutout_height = _numeric_parameter(parameter_table, "center_cutout_height_mm", "cutout_height_mm")
    thickness = _numeric_parameter(parameter_table, "back_plate_thickness_mm")
    if cutout_width is None or cutout_height is None or thickness is None:
        return _feature_result(
            expected=True,
            recognized=False,
            passed=False,
            confidence=CONFIDENCE_UNKNOWN,
            warnings=["Cutout parameters are unavailable for topology recognition."],
        )

    faces, warning = _collection(shape, "Faces")
    warnings = extraction_warnings + ([warning] if warning else [])
    x_wall_count = 0
    y_wall_count = 0
    matched_faces: list[dict[str, Any]] = []
    for index, face in enumerate(faces):
        if _geom_type(face) != "PLANE":
            continue
        box = _bbox(face)
        if not box:
            continue
        z_ok = _close(box["zlen"], thickness, max(1.0, thickness * 0.35))
        near_center = abs(box["cx"]) <= cutout_width / 2 + 2.0 and abs(box["cy"]) <= cutout_height / 2 + 2.0
        if not z_ok or not near_center:
            continue
        if box["xlen"] <= 0.25 and _close(abs(box["cx"]), cutout_width / 2, max(2.0, cutout_width * 0.08)):
            x_wall_count += 1
            matched_faces.append({"index": index, "wall": "x", "bbox": box})
        elif box["ylen"] <= 0.25 and _close(abs(box["cy"]), cutout_height / 2, max(2.0, cutout_height * 0.12)):
            y_wall_count += 1
            matched_faces.append({"index": index, "wall": "y", "bbox": box})

    recognized = x_wall_count >= 1 and y_wall_count >= 1
    confidence = CONFIDENCE_MEDIUM if recognized else CONFIDENCE_LOW
    if not recognized:
        warnings.append("Could not find enough centered vertical planar cutout walls.")

    return _feature_result(
        expected=True,
        recognized=recognized,
        passed=recognized,
        confidence=confidence,
        warnings=warnings,
        metadata={
            "matched_cutout_x_wall_faces": x_wall_count,
            "matched_cutout_y_wall_faces": y_wall_count,
            "matched_faces": matched_faces,
        },
    )


def _recognize_wall_rounded_corners(shape: Any, parameter_table: ParameterTable) -> dict[str, Any]:
    flags = feature_flags_for_parameter_table(parameter_table)
    expected = is_feature_active(flags, "rounded_corners")
    if not expected:
        return _feature_result(expected=False, recognized=False, passed=True, confidence=CONFIDENCE_HIGH)

    shape, extraction_warnings = _shape_from_model(shape)
    if shape is None:
        return _feature_result(expected=True, recognized=False, passed=False, confidence=CONFIDENCE_UNKNOWN, warnings=extraction_warnings)

    radius = _numeric_parameter(parameter_table, "corner_radius_mm")
    width = _numeric_parameter(parameter_table, "back_plate_width_mm")
    height = _numeric_parameter(parameter_table, "back_plate_height_mm")
    thickness = _numeric_parameter(parameter_table, "back_plate_thickness_mm")
    if radius is None or width is None or height is None or thickness is None or radius <= 0:
        return _feature_result(expected=True, recognized=False, passed=False, confidence=CONFIDENCE_UNKNOWN, warnings=["Rounded-corner parameters are unavailable."])

    candidates, warnings = _cylindrical_candidates(shape, "z")
    warnings.extend(extraction_warnings)
    matched = []
    for candidate in candidates:
        box = candidate["bbox"]
        if not _close(box["zlen"], thickness, max(1.0, thickness * 0.35)):
            continue
        if candidate.get("radius_estimate_mm") is not None and not _close(float(candidate["radius_estimate_mm"]), radius, max(0.75, radius * 0.35)):
            continue
        if abs(box["cx"]) < width * 0.35 or abs(box["cy"]) < height * 0.35:
            continue
        matched.append(candidate)
    recognized = len(matched) >= 4
    if not recognized:
        warnings.append(f"Expected at least four outside corner radius candidates but recognized {len(matched)}.")
    return _feature_result(
        expected=True,
        recognized=recognized,
        expected_count=4,
        recognized_count=len(matched),
        passed=recognized,
        confidence=CONFIDENCE_MEDIUM if recognized else CONFIDENCE_LOW,
        warnings=warnings,
        metadata={"matched_corner_candidates": matched},
    )


def recognize_solid_connectivity(shape: Any) -> dict[str, Any]:
    """Recognize whether a shape is one connected valid solid where available."""

    inspection = inspect_shape(shape)
    warnings = [f"{warning.metric}: {warning.message}" for warning in inspection.warnings]
    solid_count = inspection.solid_count
    connected = solid_count == 1 if solid_count is not None else False
    passed = connected and inspection.is_valid is not False
    if solid_count is None:
        warnings.append("Solid count is unavailable; connected-solid recognition is low confidence.")
    return {
        "solid_count": solid_count,
        "connected_solid": connected,
        "valid_shape": inspection.is_valid,
        "passed": passed if solid_count is not None else False,
        "confidence": CONFIDENCE_HIGH if solid_count is not None else CONFIDENCE_UNKNOWN,
        "warnings": warnings,
    }


def recognize_l_bracket_gusset(shape: Any, parameter_table: ParameterTable) -> dict[str, Any]:
    """Recognize an L-bracket triangular gusset using sloped planar-face candidates."""

    flags = feature_flags_for_parameter_table(parameter_table)
    expected = is_feature_active(flags, "triangular_gusset") and _boolean_parameter(parameter_table, "gusset_enabled", True)
    if not expected:
        return _feature_result(expected=False, recognized=False, passed=True, confidence=CONFIDENCE_HIGH)

    shape, extraction_warnings = _shape_from_model(shape)
    if shape is None:
        return _feature_result(expected=True, recognized=False, passed=False, confidence=CONFIDENCE_UNKNOWN, warnings=extraction_warnings)

    gusset_height = _numeric_parameter(parameter_table, "gusset_height_mm")
    gusset_thickness = _numeric_parameter(parameter_table, "gusset_thickness_mm")
    thickness = _numeric_parameter(parameter_table, "thickness_mm")
    if gusset_height is None or gusset_thickness is None or thickness is None:
        return _feature_result(expected=True, recognized=False, passed=False, confidence=CONFIDENCE_UNKNOWN, warnings=["Gusset parameters are unavailable."])

    expected_span = max(gusset_height - thickness, 0.0)
    faces, warning = _collection(shape, "Faces")
    warnings = extraction_warnings + ([warning] if warning else [])
    matched_faces: list[dict[str, Any]] = []
    for index, face in enumerate(faces):
        if _geom_type(face) != "PLANE":
            continue
        box = _bbox(face)
        if not box:
            continue
        x_ok = _close(box["xlen"], expected_span, max(2.0, expected_span * 0.2))
        z_ok = _close(box["zlen"], expected_span, max(2.0, expected_span * 0.2))
        y_ok = box["ylen"] <= gusset_thickness + max(2.0, gusset_thickness * 0.5)
        inside_corner = box["xmin"] >= thickness - 1.0 and box["zmin"] >= thickness - 1.0
        if x_ok and z_ok and y_ok and inside_corner:
            matched_faces.append({"index": index, "bbox": box, "area_mm2": _safe_area(face)})

    recognized = bool(matched_faces)
    if not recognized:
        warnings.append("Could not find a sloped planar triangular-gusset face near the inside corner.")
    return _feature_result(
        expected=True,
        recognized=recognized,
        expected_count=1,
        recognized_count=len(matched_faces),
        passed=recognized,
        confidence=CONFIDENCE_MEDIUM if recognized else CONFIDENCE_LOW,
        warnings=warnings,
        metadata={"matched_gusset_faces": matched_faces},
    )


def _wall_through_holes(shape: Any, parameter_table: ParameterTable) -> dict[str, Any]:
    flags = feature_flags_for_parameter_table(parameter_table)
    expected_active = is_feature_active(flags, "mounting_holes")
    expected_count = _integer_parameter(parameter_table, "mounting_hole_count", 0) if expected_active else 0
    if not expected_active:
        return _feature_result(expected_count=0, recognized_count=0, passed=True, confidence=CONFIDENCE_HIGH)
    return recognize_through_holes(
        shape,
        "z",
        expected_count=expected_count,
        expected_diameter_mm=_numeric_parameter(parameter_table, "mounting_hole_diameter_mm"),
        expected_centers=_wall_expected_hole_centers(parameter_table),
        center_axes=("x", "y"),
        through_length_mm=_numeric_parameter(parameter_table, "back_plate_thickness_mm"),
    )


def _l_base_holes(shape: Any, parameter_table: ParameterTable) -> dict[str, Any]:
    flags = feature_flags_for_parameter_table(parameter_table)
    expected_active = is_feature_active(flags, "base_mounting_holes")
    expected_count = _integer_parameter(parameter_table, "base_hole_count", 0) if expected_active else 0
    if not expected_active or expected_count == 0:
        return _feature_result(expected_count=0, recognized_count=0, passed=True, confidence=CONFIDENCE_HIGH)
    return recognize_through_holes(
        shape,
        "z",
        expected_count=expected_count,
        expected_diameter_mm=_numeric_parameter(parameter_table, "hole_diameter_mm"),
        expected_centers=_l_base_expected_hole_centers(parameter_table),
        center_axes=("x", "y"),
        through_length_mm=_numeric_parameter(parameter_table, "thickness_mm"),
    )


def _l_vertical_holes(shape: Any, parameter_table: ParameterTable) -> dict[str, Any]:
    flags = feature_flags_for_parameter_table(parameter_table)
    expected_active = is_feature_active(flags, "vertical_mounting_holes")
    expected_count = _integer_parameter(parameter_table, "vertical_hole_count", 0) if expected_active else 0
    if not expected_active or expected_count == 0:
        return _feature_result(expected_count=0, recognized_count=0, passed=True, confidence=CONFIDENCE_HIGH)
    return recognize_through_holes(
        shape,
        "x",
        expected_count=expected_count,
        expected_diameter_mm=_numeric_parameter(parameter_table, "hole_diameter_mm"),
        expected_centers=_l_vertical_expected_hole_centers(parameter_table),
        center_axes=("y", "z"),
        through_length_mm=_numeric_parameter(parameter_table, "thickness_mm"),
    )


def recognize_wall_bracket_features(
    shape: Any,
    parameter_table: ParameterTable,
    feature_plan: Any | None = None,
) -> dict[str, Any]:
    """Recognize expected wall-mounted bracket features from CAD topology."""

    del feature_plan
    topology = recognize_solid_connectivity(shape)
    recognized_features = {
        "through_holes": _wall_through_holes(shape, parameter_table),
        "center_cutout": recognize_center_cutout(shape, parameter_table),
        "rounded_corners": _recognize_wall_rounded_corners(shape, parameter_table),
    }
    return _build_report("wall_mounted_bracket", recognized_features, topology, parameter_table)


def recognize_l_bracket_features(
    shape: Any,
    parameter_table: ParameterTable,
    feature_plan: Any | None = None,
) -> dict[str, Any]:
    """Recognize expected L-bracket topology and supported optional features."""

    del feature_plan
    topology = recognize_solid_connectivity(shape)
    recognized_features = {
        "solid_connection": _feature_result(
            expected=True,
            recognized=bool(topology.get("connected_solid")),
            passed=bool(topology.get("connected_solid")),
            confidence=topology.get("confidence", CONFIDENCE_UNKNOWN),
            warnings=topology.get("warnings", []),
            metadata={"solid_count": topology.get("solid_count")},
        ),
        "base_through_holes": _l_base_holes(shape, parameter_table),
        "vertical_through_holes": _l_vertical_holes(shape, parameter_table),
        "triangular_gusset": recognize_l_bracket_gusset(shape, parameter_table),
    }
    return _build_report("l_bracket", recognized_features, topology, parameter_table)


def recognize_features(
    shape: Any,
    parameter_table: ParameterTable,
    feature_plan: Any | None = None,
) -> dict[str, Any]:
    """Recognize feature topology for a supported model family."""

    if parameter_table.family == "l_bracket":
        return recognize_l_bracket_features(shape, parameter_table, feature_plan)
    if parameter_table.family == "wall_mounted_bracket":
        return recognize_wall_bracket_features(shape, parameter_table, feature_plan)
    return FeatureRecognitionReport(
        object_type=parameter_table.family,
        passed=False,
        warnings=[f"Unsupported model family for feature recognition: {parameter_table.family}"],
    ).model_dump(mode="json")


def _build_report(
    object_type: str,
    recognized_features: dict[str, dict[str, Any]],
    topology: dict[str, Any],
    parameter_table: ParameterTable,
) -> dict[str, Any]:
    warnings: list[str] = []
    for feature_name, result in recognized_features.items():
        warnings.extend(f"{feature_name}: {warning}" for warning in result.get("warnings", []))
    warnings.extend(f"topology: {warning}" for warning in topology.get("warnings", []))

    # Low-confidence failures are still surfaced as warnings in Phase 18. This
    # avoids turning approximate recognition into a brittle release gate.
    hard_failures = [
        name
        for name, result in recognized_features.items()
        if result.get("passed") is False and result.get("confidence") in {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM}
    ]
    passed = not hard_failures and bool(topology.get("connected_solid", True))
    if hard_failures:
        warnings.append(f"Feature recognition hard failures: {', '.join(hard_failures)}")

    report = FeatureRecognitionReport(
        object_type=object_type,
        recognized_features=recognized_features,
        topology_checks={
            "solid_count": topology.get("solid_count"),
            "connected_solid": topology.get("connected_solid"),
            "valid_shape": topology.get("valid_shape"),
            "passed": topology.get("passed"),
            "confidence": topology.get("confidence"),
        },
        passed=passed,
        warnings=warnings,
        metadata={
            "recognizer": "topology_feature_recognizer_phase_18",
            "parameter_family": parameter_table.family,
            "feature_flags": feature_flags_for_parameter_table(parameter_table),
        },
    )
    return report.model_dump(mode="json")


def write_feature_recognition_report(report: dict[str, Any], path: str | Path) -> Path:
    """Write a feature recognition report to JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def write_feature_recognition_summary(report: dict[str, Any], path: str | Path) -> Path:
    """Write a compact human-readable feature recognition summary."""

    lines = [
        f"Feature recognition report: {report.get('object_type')}",
        f"Passed: {str(report.get('passed')).lower()}",
        "Recognized features:",
    ]
    for name, result in report.get("recognized_features", {}).items():
        status = "passed" if result.get("passed") else "warning"
        count = ""
        if "expected_count" in result or "recognized_count" in result:
            count = f" expected={result.get('expected_count')} recognized={result.get('recognized_count')}"
        lines.append(f"  - {name}: {status}, confidence={result.get('confidence')}{count}")
    topology = report.get("topology_checks", {})
    lines.extend(
        [
            "Topology:",
            f"  - solid_count: {topology.get('solid_count')}",
            f"  - connected_solid: {topology.get('connected_solid')}",
            f"  - valid_shape: {topology.get('valid_shape')}",
        ]
    )
    warnings = report.get("warnings", [])
    lines.append("Warnings:")
    if warnings:
        lines.extend(f"  - {warning}" for warning in warnings)
    else:
        lines.append("  - none")
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
