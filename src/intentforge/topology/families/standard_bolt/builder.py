"""Deterministic CadQuery macro-geometry builder for a registered bolt."""

from __future__ import annotations

from typing import Any

from intentforge.schemas import FeaturePlan, ParameterTable


def _numeric(table: ParameterTable, name: str) -> float:
    value = table.get(name).value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def build_standard_bolt(table: ParameterTable, feature_plan: FeaturePlan | None = None) -> Any:
    """Build shank, simplified thread cylinder, and selected head macro-geometry."""

    if table.family != "standard_bolt":
        raise ValueError("standard bolt factory received the wrong family")
    try:
        import cadquery as cq
    except ImportError as exc:
        from intentforge.generator.cadquery_generator import CadQueryUnavailableError

        raise CadQueryUnavailableError('CadQuery is required to build standard_bolt. Install "intentforge[cad]".') from exc

    diameter = _numeric(table, "nominal_diameter")
    pitch = _numeric(table, "thread_pitch")
    shank_length = _numeric(table, "shank_length")
    thread_length = _numeric(table, "thread_length")
    head_type = table.get("head_type").value
    if head_type not in {"hexagonal", "socket_cap"}:
        raise ValueError("head_type is not supported")
    if pitch >= diameter / 2.0 or shank_length + thread_length <= 0:
        raise ValueError("bolt dimensions do not define valid macro-geometry")

    shaft = cq.Workplane("XY").circle(diameter / 2.0).extrude(shank_length + thread_length)
    head_height = 0.65 * diameter if head_type == "hexagonal" else diameter
    head_plane = cq.Workplane("XY").workplane(offset=shank_length + thread_length)
    if head_type == "hexagonal":
        head = head_plane.polygon(6, 1.8 * diameter).extrude(head_height)
    else:
        head = head_plane.circle(0.75 * diameter).extrude(head_height)
    return shaft.union(head)
