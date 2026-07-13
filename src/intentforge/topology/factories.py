"""Closed geometry-factory dispatch for declarative topology profiles."""

from __future__ import annotations

from typing import Any, Callable

from intentforge.topology.registry import get_topology_registry
from intentforge.schemas import FeaturePlan, ParameterTable


def _wall(table: ParameterTable, plan: FeaturePlan | None) -> Any:
    from intentforge.generator.cadquery_generator import build_wall_bracket

    return build_wall_bracket(table)


def _l_bracket(table: ParameterTable, plan: FeaturePlan | None) -> Any:
    from intentforge.generator.cadquery_generator import build_l_bracket

    return build_l_bracket(table, plan)


def _flange(table: ParameterTable, plan: FeaturePlan | None) -> Any:
    from intentforge.topology.families.industrial_flange.geometry_factory import build_industrial_flange

    return build_industrial_flange(table, plan)


def _spur_gear(table: ParameterTable, plan: FeaturePlan | None) -> Any:
    from intentforge.topology.families.spur_gear.builder import build_spur_gear

    return build_spur_gear(table, plan)


def _standard_bolt(table: ParameterTable, plan: FeaturePlan | None) -> Any:
    from intentforge.topology.families.standard_bolt.builder import build_standard_bolt

    return build_standard_bolt(table, plan)


_FACTORIES: dict[str, Callable[[ParameterTable, FeaturePlan | None], Any]] = {
    "wall_bracket_factory_v1": _wall,
    "l_bracket_factory_v1": _l_bracket,
    "industrial_flange_factory_v1": _flange,
    "spur_gear_factory_v1": _spur_gear,
    "standard_bolt_factory_v1": _standard_bolt,
}


def build_registered_model(parameter_table: ParameterTable, feature_plan: FeaturePlan | None = None) -> Any:
    manifest = get_topology_registry().get(parameter_table.family)
    if feature_plan is not None and feature_plan.family != manifest.topology_family:
        raise ValueError("feature plan and parameter table families do not match")
    factory = _FACTORIES.get(manifest.geometry_factory_id)
    if factory is None:
        raise ValueError(f"geometry factory is not registered: {manifest.geometry_factory_id}")
    return factory(parameter_table, feature_plan)
