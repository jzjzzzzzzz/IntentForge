"""Reusable topology-informed shape inspection for CadQuery/OpenCascade models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from harness.reports import ShapeInspectionReport, TopologyMetric, TopologyWarning


def _warning(metric: str, message: str) -> TopologyWarning:
    return TopologyWarning(metric=metric, message=message)


def _metric(
    name: str,
    value: Any,
    *,
    unit: str | None = None,
    available: bool = True,
    description: str = "",
) -> TopologyMetric:
    return TopologyMetric(
        name=name,
        value=value,
        unit=unit,
        available=available,
        description=description,
    )


def _shape_from_model(model: Any) -> tuple[Any | None, list[TopologyWarning]]:
    warnings: list[TopologyWarning] = []
    if model is None:
        return None, [_warning("shape", "No model or shape was provided.")]

    if hasattr(model, "val") and callable(model.val):
        try:
            return model.val(), warnings
        except Exception as exc:  # pragma: no cover - CadQuery exception types vary
            warnings.append(_warning("shape", f"Could not extract shape with val(): {exc}"))
            return None, warnings

    return model, warnings


def _call_method(shape: Any, method_names: tuple[str, ...], metric_name: str) -> tuple[Any | None, TopologyWarning | None]:
    for method_name in method_names:
        method = getattr(shape, method_name, None)
        if method is None:
            continue
        if not callable(method):
            return method, None
        try:
            return method(), None
        except TypeError:
            continue
        except Exception as exc:  # pragma: no cover - OpenCascade failures are environment-specific
            return None, _warning(metric_name, f"{method_name}() failed: {exc}")

    return None, _warning(metric_name, f"No supported method found for {metric_name}.")


def _float_attr(obj: Any, attr: str) -> float | None:
    value = getattr(obj, attr, None)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _vector_dict(vector: Any) -> dict[str, float] | None:
    values = {
        axis: _float_attr(vector, axis)
        for axis in ("x", "y", "z")
    }
    if any(value is None for value in values.values()):
        return None
    return {axis: float(value) for axis, value in values.items() if value is not None}


def _collection_count(shape: Any, method_name: str, metric_name: str) -> tuple[int | None, TopologyWarning | None]:
    collection, warning = _call_method(shape, (method_name,), metric_name)
    if warning is not None:
        return None, warning
    try:
        return len(collection), None
    except TypeError:
        size = getattr(collection, "size", None)
        if callable(size):
            try:
                return int(size()), None
            except Exception as exc:  # pragma: no cover - backend-specific
                return None, _warning(metric_name, f"Could not read {method_name} collection size: {exc}")
        return None, _warning(metric_name, f"{method_name}() did not return a countable collection.")


def _add_unavailable_metric(report: ShapeInspectionReport, name: str, warning: TopologyWarning, unit: str | None = None) -> None:
    report.metrics.append(_metric(name, None, unit=unit, available=False))
    report.warnings.append(warning)


def inspect_shape(model: Any, family: str | None = None) -> ShapeInspectionReport:
    """Inspect a CadQuery Workplane, CadQuery shape, or shape-like object.

    The inspector is intentionally defensive. OpenCascade topology access can
    vary across wrapped shape types, so unavailable metrics are recorded as
    warnings instead of raising.
    """

    shape, extraction_warnings = _shape_from_model(model)
    report = ShapeInspectionReport(family=family, warnings=extraction_warnings)
    if shape is None:
        report.metrics.append(_metric("shape", None, available=False))
        return report

    report.shape_type = type(shape).__name__

    bbox, bbox_warning = _call_method(shape, ("BoundingBox",), "bounding_box")
    if bbox_warning is not None or bbox is None:
        _add_unavailable_metric(report, "bounding_box_dimensions", bbox_warning or _warning("bounding_box", "Bounding box unavailable."), unit="mm")
    else:
        dimensions = {
            "x": _float_attr(bbox, "xlen"),
            "y": _float_attr(bbox, "ylen"),
            "z": _float_attr(bbox, "zlen"),
        }
        if any(value is None for value in dimensions.values()):
            _add_unavailable_metric(
                report,
                "bounding_box_dimensions",
                _warning("bounding_box", "Bounding box did not expose xlen, ylen, and zlen."),
                unit="mm",
            )
        else:
            report.bounding_box_dimensions_mm = {
                axis: float(value)
                for axis, value in dimensions.items()
                if value is not None
            }
            report.bounding_box_min_mm = {
                axis: value
                for axis, attr in {"x": "xmin", "y": "ymin", "z": "zmin"}.items()
                if (value := _float_attr(bbox, attr)) is not None
            } or None
            report.bounding_box_max_mm = {
                axis: value
                for axis, attr in {"x": "xmax", "y": "ymax", "z": "zmax"}.items()
                if (value := _float_attr(bbox, attr)) is not None
            } or None
            report.metrics.append(
                _metric(
                    "bounding_box_dimensions",
                    report.bounding_box_dimensions_mm,
                    unit="mm",
                    description="Axis-aligned bounding box dimensions.",
                )
            )

    volume, volume_warning = _call_method(shape, ("Volume",), "volume")
    if volume_warning is not None or isinstance(volume, bool) or not isinstance(volume, int | float):
        _add_unavailable_metric(report, "volume", volume_warning or _warning("volume", "Volume was not numeric."), unit="mm^3")
    else:
        report.volume_mm3 = float(volume)
        report.metrics.append(_metric("volume", report.volume_mm3, unit="mm^3"))

    area, area_warning = _call_method(shape, ("Area",), "surface_area")
    if area_warning is not None or isinstance(area, bool) or not isinstance(area, int | float):
        _add_unavailable_metric(report, "surface_area", area_warning or _warning("surface_area", "Surface area was not numeric."), unit="mm^2")
    else:
        report.surface_area_mm2 = float(area)
        report.metrics.append(_metric("surface_area", report.surface_area_mm2, unit="mm^2"))

    count_specs: tuple[tuple[str, str, str], ...] = (
        ("solid_count", "Solids", "solid_count"),
        ("face_count", "Faces", "face_count"),
        ("edge_count", "Edges", "edge_count"),
        ("vertex_count", "Vertices", "vertex_count"),
    )
    for field_name, method_name, metric_name in count_specs:
        count, count_warning = _collection_count(shape, method_name, metric_name)
        if count_warning is not None or count is None:
            _add_unavailable_metric(report, metric_name, count_warning or _warning(metric_name, "Topology count unavailable."))
            continue
        setattr(report, field_name, count)
        report.metrics.append(_metric(metric_name, count))

    is_valid, valid_warning = _call_method(shape, ("isValid", "IsValid"), "is_valid")
    if valid_warning is not None or not isinstance(is_valid, bool):
        _add_unavailable_metric(report, "is_valid", valid_warning or _warning("is_valid", "Validity result was not boolean."))
    else:
        report.is_valid = is_valid
        report.metrics.append(_metric("is_valid", is_valid))

    center, center_warning = _call_method(shape, ("Center", "CenterOfMass", "centerOfMass"), "center_of_mass")
    center_dict = _vector_dict(center) if center is not None else None
    if center_warning is not None or center_dict is None:
        _add_unavailable_metric(
            report,
            "center_of_mass",
            center_warning or _warning("center_of_mass", "Center of mass did not expose x, y, and z."),
            unit="mm",
        )
    else:
        report.center_of_mass_mm = center_dict
        report.metrics.append(_metric("center_of_mass", center_dict, unit="mm"))

    return report


def write_shape_inspection_report(report: ShapeInspectionReport, path: str | Path) -> Path:
    """Write a shape inspection report to JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
