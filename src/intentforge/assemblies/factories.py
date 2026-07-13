"""Closed geometry dispatch and placement for registered assemblies."""

from __future__ import annotations

import math
from typing import Any

from intentforge.schemas import ParameterTable


def _numeric(table: ParameterTable, name: str) -> float:
    value = table.get(name).value
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def build_flange_bolted_joint(
    tables: dict[str, ParameterTable],
    models: dict[str, Any],
) -> tuple[Any, list[dict[str, Any]]]:
    """Place one bolt concentrically in every flange bolt hole."""

    try:
        import cadquery as cq
    except ImportError as exc:
        from intentforge.generator.cadquery_generator import CadQueryUnavailableError

        raise CadQueryUnavailableError('CadQuery is required to build assemblies. Install "intentforge[cad]".') from exc

    flange_table = tables["flange"]
    bolt_table = tables["bolt"]
    hole_count = int(flange_table.get("hole_count").value)
    radius = _numeric(flange_table, "bolt_circle_diameter") / 2.0
    flange_thickness = _numeric(flange_table, "flange_thickness")
    bolt_body_length = _numeric(bolt_table, "shank_length") + _numeric(bolt_table, "thread_length")
    bolt_z = flange_thickness - bolt_body_length

    assembly = cq.Assembly(name="flange_bolted_joint")
    assembly.add(models["flange"], name="flange")
    placements = [{"instance_id": "flange_001", "component_id": "flange", "location": [0.0, 0.0, 0.0]}]
    for index in range(hole_count):
        angle = 2.0 * math.pi * index / hole_count
        location = (
            radius * math.cos(angle),
            radius * math.sin(angle),
            bolt_z,
        )
        assembly.add(
            models["bolt"],
            name=f"bolt_{index + 1:03d}",
            loc=cq.Location(cq.Vector(*location)),
        )
        placements.append({
            "instance_id": f"bolt_{index + 1:03d}",
            "component_id": "bolt",
            "location": [round(item, 12) for item in location],
        })
    return assembly, placements


def build_registered_assembly(factory_id: str, tables: dict[str, ParameterTable], models: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    factories = {"flange_bolted_joint_factory_v1": build_flange_bolted_joint}
    factory = factories.get(factory_id)
    if factory is None:
        raise ValueError(f"assembly factory is not registered: {factory_id}")
    return factory(tables, models)
