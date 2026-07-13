"""Deterministic CadQuery builder for a registered spur gear."""

from __future__ import annotations

import math
from typing import Any

from intentforge.schemas import FeaturePlan, ParameterTable


def _numeric(table: ParameterTable, name: str) -> float:
    value = table.get(name).value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _involute_profile(module: float, teeth: int, pressure_angle: float) -> list[tuple[float, float]]:
    """Return a closed, deterministic involute-approximated transverse profile."""

    pitch_radius = module * teeth / 2.0
    root_radius = module * (teeth - 2.5) / 2.0
    outer_radius = pitch_radius + module
    base_radius = pitch_radius * math.cos(math.radians(pressure_angle))
    flank_base_radius = max(root_radius, base_radius)
    alpha = math.radians(pressure_angle)
    pitch_involute = math.tan(alpha) - alpha
    half_tooth_pitch = math.pi / (2.0 * teeth)

    def half_angle(radius: float) -> float:
        if radius <= base_radius:
            involute = 0.0
        else:
            parameter = math.sqrt(max(0.0, (radius / base_radius) ** 2 - 1.0))
            involute = parameter - math.atan(parameter)
        return max(half_tooth_pitch * 0.2, half_tooth_pitch + pitch_involute - involute)

    points: list[tuple[float, float]] = []
    pitch = 2.0 * math.pi / teeth
    flank_radii = (root_radius, flank_base_radius, pitch_radius, outer_radius)
    for index in range(teeth):
        center = index * pitch
        for radius in flank_radii:
            angle = center - half_angle(radius)
            points.append((radius * math.cos(angle), radius * math.sin(angle)))
        for radius in reversed(flank_radii):
            angle = center + half_angle(radius)
            points.append((radius * math.cos(angle), radius * math.sin(angle)))
    return points


def build_spur_gear(table: ParameterTable, feature_plan: FeaturePlan | None = None) -> Any:
    """Build one external spur gear with an involute-approximated tooth profile."""

    if table.family != "spur_gear":
        raise ValueError("spur gear factory received the wrong family")
    try:
        import cadquery as cq
    except ImportError as exc:
        from intentforge.generator.cadquery_generator import CadQueryUnavailableError

        raise CadQueryUnavailableError('CadQuery is required to build spur_gear. Install "intentforge[cad]".') from exc

    module = _numeric(table, "module")
    pressure_angle = _numeric(table, "pressure_angle")
    face_width = _numeric(table, "face_width")
    bore = _numeric(table, "bore_diameter")
    bore_clearance = _numeric(table, "bore_clearance")
    effective_bore = bore + bore_clearance
    raw_teeth = table.get("teeth_count").value
    if isinstance(raw_teeth, bool) or not isinstance(raw_teeth, int):
        raise ValueError("teeth_count must be an integer")
    root_diameter = (raw_teeth - 2.5) * module
    from intentforge.topology.registry import get_topology_registry

    margin_modules = float(
        get_topology_registry().get("spur_gear").metadata["minimum_radial_bore_margin_modules"]
    )
    if raw_teeth < 17:
        raise ValueError("zero-shift spur gears require at least 17 teeth to avoid undercut")
    if bore <= 0 or bore_clearance < 0 or effective_bore + 2.0 * margin_modules * module >= root_diameter:
        raise ValueError("gear parameters do not retain the required bore-to-root material margin")
    if not 14.5 <= pressure_angle <= 30.0:
        raise ValueError("pressure_angle is outside the supported approximation range")

    profile = _involute_profile(module, raw_teeth, pressure_angle)
    return (
        cq.Workplane("XY")
        .polyline(profile)
        .close()
        .extrude(face_width)
        .faces(">Z")
        .workplane()
        .hole(effective_bore)
    )
