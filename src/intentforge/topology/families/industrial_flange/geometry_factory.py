"""Deterministic CadQuery factory for the registered industrial flange."""

from __future__ import annotations

import math
from typing import Any

from intentforge.schemas import FeaturePlan, ParameterTable


def _numeric(table: ParameterTable, name: str) -> float:
    value = table.get(name).value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def build_industrial_flange(table: ParameterTable, feature_plan: FeaturePlan | None = None) -> Any:
    """Build a flat ring flange with a polar through-hole pattern."""

    if table.family != "industrial_flange":
        raise ValueError("industrial flange factory received the wrong family")
    try:
        import cadquery as cq
    except ImportError as exc:
        from intentforge.generator.cadquery_generator import CadQueryUnavailableError

        raise CadQueryUnavailableError(
            'CadQuery is required to build industrial_flange. Install "intentforge[cad]".'
        ) from exc

    outer = _numeric(table, "flange_outer_diameter")
    bolt_circle = _numeric(table, "bolt_circle_diameter")
    bolt_hole = _numeric(table, "bolt_hole_diameter")
    thickness = _numeric(table, "flange_thickness")
    bore = _numeric(table, "bore_diameter")
    bore_clearance = _numeric(table, "bore_clearance")
    effective_bore = bore + bore_clearance
    raw_count = table.get("hole_count").value
    if isinstance(raw_count, bool) or not isinstance(raw_count, int):
        raise ValueError("hole_count must be an integer")
    if bore_clearance < 0 or effective_bore >= outer or bolt_circle + bolt_hole >= outer or bolt_circle - bolt_hole <= effective_bore:
        raise ValueError("flange diameters do not leave valid radial material")
    if raw_count < 3:
        raise ValueError("hole_count must be at least 3")

    model = cq.Workplane("XY").circle(outer / 2.0).circle(effective_bore / 2.0).extrude(thickness)
    radius = bolt_circle / 2.0
    points = [
        (radius * math.cos(2.0 * math.pi * index / raw_count), radius * math.sin(2.0 * math.pi * index / raw_count))
        for index in range(raw_count)
    ]
    return model.faces(">Z").workplane().pushPoints(points).hole(bolt_hole)
