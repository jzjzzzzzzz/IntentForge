"""Manifest-driven parser for registered topology parameter payloads."""

from __future__ import annotations

import re
from typing import Any

from intentforge.features import make_feature_flag
from intentforge.topology.registry import TopologyRegistryError, get_topology_registry
from intentforge.schemas import (
    Constraint,
    ConstraintGraph,
    FeaturePlan,
    FeatureStep,
    IntentSpec,
    Parameter,
    ParameterTable,
)


def _coerce(definition: Any, value: Any) -> float | int | bool | str:
    if definition.parameter_type == "float":
        if isinstance(value, bool):
            raise ValueError(f"{definition.name} must be numeric")
        result: float | int | bool | str = float(value)
    elif definition.parameter_type == "integer":
        if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{definition.name} must be an integer")
        result = int(value)
    elif definition.parameter_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{definition.name} must be boolean")
        result = value
    else:
        if not isinstance(value, str):
            raise ValueError(f"{definition.name} must be a string")
        result = value
    if definition.safe_bounds is not None:
        low, high = definition.safe_bounds
        if not low <= float(result) <= high:
            raise ValueError(f"{definition.name} is outside safe bounds {low}..{high}")
    return result


def _feature_flags(manifest: Any, requested: dict[str, Any]) -> dict[str, dict[str, Any]]:
    flags: dict[str, dict[str, Any]] = {}
    for feature in manifest.supported_features:
        enabled = requested.get(feature.feature_id, feature.default_enabled)
        if not isinstance(enabled, bool):
            raise ValueError(f"feature {feature.feature_id} must be boolean")
        flags[feature.feature_id] = make_feature_flag(
            "requested_by_user" if feature.feature_id in requested and enabled else
            "defaulted_by_system" if enabled else "omitted",
            "Feature state was validated against the registered topology manifest.",
        )
    unknown = sorted(set(requested) - {item.feature_id for item in manifest.supported_features})
    if unknown:
        raise ValueError(f"unsupported features for {manifest.topology_family}: {', '.join(unknown)}")
    return flags


def parse_registered_intent(payload: dict[str, Any]):
    """Build normal IntentForge artifacts from one validated topology payload."""

    from intentforge.parser.requirement_parser import ParsedPrompt, UnsupportedObjectError

    allowed = {"family", "object_type", "parameters", "features", "objective", "requirements", "user_prompt"}
    unknown_fields = sorted(set(payload) - allowed)
    if unknown_fields:
        raise ValueError(f"unknown intent fields: {', '.join(unknown_fields)}")
    family = str(payload.get("family") or payload.get("object_type") or "")
    try:
        manifest = get_topology_registry().get(family)
    except TopologyRegistryError as exc:
        raise UnsupportedObjectError(str(exc)) from exc
    raw_parameters = payload.get("parameters") or {}
    raw_features = payload.get("features") or {}
    if not isinstance(raw_parameters, dict) or not isinstance(raw_features, dict):
        raise ValueError("parameters and features must be mappings")
    unknown_parameters = sorted(set(raw_parameters) - {item.name for item in manifest.controlled_parameters})
    if unknown_parameters:
        raise ValueError(f"unsupported parameters for {family}: {', '.join(unknown_parameters)}")

    parameters: list[Parameter] = []
    assumptions: list[str] = []
    for definition in manifest.controlled_parameters:
        supplied = definition.name in raw_parameters
        value = _coerce(definition, raw_parameters.get(definition.name, definition.default))
        if not supplied:
            assumptions.append(f"{definition.name} defaulted to the topology manifest value.")
        parameters.append(
            Parameter(
                name=definition.name,
                value=value,
                unit=definition.unit,
                description=definition.description,
                source="user" if supplied else "default",
                reason="Controlled by the registered topology manifest.",
                min_value=definition.safe_bounds[0] if definition.safe_bounds else None,
                max_value=definition.safe_bounds[1] if definition.safe_bounds else None,
            )
        )
    flags = _feature_flags(manifest, raw_features)
    table = ParameterTable(
        family=family,
        parameters=parameters,
        assumptions=assumptions,
        metadata={
            "parser": manifest.parser_id,
            "topology_manifest_version": manifest.manifest_version,
            "feature_flags": flags,
        },
    )
    steps: list[FeatureStep] = []
    previous: list[str] = []
    for feature in manifest.supported_features:
        if flags[feature.feature_id]["state"] == "omitted":
            continue
        step_id = f"apply_{feature.feature_id}"
        steps.append(
            FeatureStep(
                id=step_id,
                operation=feature.operation,
                parameters=feature.parameter_names,
                depends_on=previous[-1:] if previous else [],
                reason=feature.description,
                outputs=[f"{feature.feature_id}_result"],
                validation_refs=[f"{feature.feature_id}_registered"],
            )
        )
        previous.append(step_id)
    plan = FeaturePlan(
        family=family,
        construction_strategy=f"Execute the ordered feature adapters declared by {family}@{manifest.manifest_version}.",
        steps=steps,
        assumptions=assumptions,
        metadata={"topology_manifest_version": manifest.manifest_version},
    )
    constraints = [
        Constraint(
            id=f"{definition.name}_safe_bounds",
            kind="dimensional",
            expression=f"{definition.safe_bounds[0]} <= {definition.name} <= {definition.safe_bounds[1]}",
            parameters=[definition.name],
            reason="The registered topology manifest defines a conservative physical input boundary.",
        )
        for definition in manifest.controlled_parameters
        if definition.safe_bounds is not None
    ]
    if family == "industrial_flange":
        constraints.extend(
            [
                Constraint(
                    id="flange_outer_material",
                    kind="geometric",
                    expression="bolt_circle_diameter + bolt_hole_diameter < flange_outer_diameter",
                    parameters=["bolt_circle_diameter", "bolt_hole_diameter", "flange_outer_diameter"],
                    reason="Bolt holes must remain inside the flange outside diameter.",
                ),
                Constraint(
                    id="flange_inner_material",
                    kind="geometric",
                    expression="bore_diameter + bolt_hole_diameter < bolt_circle_diameter",
                    parameters=["bore_diameter", "bolt_hole_diameter", "bolt_circle_diameter"],
                    reason="Bolt holes must remain outside the central bore.",
                ),
            ]
        )
    graph = ConstraintGraph(
        family=family,
        nodes=[item.name for item in parameters],
        dependencies={},
        constraints=constraints,
        assumptions=assumptions,
        metadata={"topology_manifest_version": manifest.manifest_version},
    )
    prompt = str(payload.get("user_prompt") or f"Structured {family} design intent")
    intent = IntentSpec(
        family=family,
        user_prompt=prompt,
        objective=str(payload.get("objective") or f"Generate a deterministic registered {manifest.title} model."),
        requirements=[str(item) for item in payload.get("requirements", [])] or [
            f"Use topology manifest {family}@{manifest.manifest_version}.",
            "Keep all controlled parameters inside declared safe bounds.",
        ],
        assumptions=assumptions,
        metadata={
            "parser": manifest.parser_id,
            "topology_manifest_version": manifest.manifest_version,
            "feature_flags": flags,
        },
    )
    return ParsedPrompt(intent=intent, parameter_table=table, constraint_graph=graph, feature_plan=plan, warnings=[])


def parse_registered_prompt(prompt: str, family: str):
    """Parse labeled dimensions from text using manifest names, then validate."""

    manifest = get_topology_registry().get(family)
    normalized = prompt.lower().replace("-", " ")
    values: dict[str, Any] = {}
    for definition in manifest.controlled_parameters:
        labels = {definition.name.replace("_", " ")}
        if definition.name.endswith("_diameter"):
            labels.add(definition.name.removesuffix("_diameter").replace("_", " ") + " diameter")
        for label in sorted(labels, key=len, reverse=True):
            match = re.search(rf"\b{re.escape(label)}\b\s*(?:is|=|of)?\s*(-?\d+(?:\.\d+)?)", normalized)
            if match:
                values[definition.name] = float(match.group(1))
                break
    return parse_registered_intent({"family": family, "parameters": values, "user_prompt": prompt})


def build_registered_intent_json_schema(family: str) -> dict[str, Any]:
    """Return a deterministic JSON Schema derived from one active manifest."""

    manifest = get_topology_registry().get(family)
    type_map = {"float": "number", "integer": "integer", "boolean": "boolean", "string": "string"}
    parameter_properties: dict[str, Any] = {}
    for item in manifest.controlled_parameters:
        field: dict[str, Any] = {
            "type": type_map[item.parameter_type],
            "default": item.default,
            "description": item.description,
        }
        if item.safe_bounds:
            field.update({"minimum": item.safe_bounds[0], "maximum": item.safe_bounds[1]})
        parameter_properties[item.name] = field
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"intentforge:topology:{manifest.topology_family}:{manifest.manifest_version}",
        "type": "object",
        "additionalProperties": False,
        "required": ["family", "parameters"],
        "properties": {
            "family": {"const": manifest.topology_family},
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": parameter_properties,
            },
            "features": {
                "type": "object",
                "additionalProperties": False,
                "properties": {item.feature_id: {"type": "boolean"} for item in manifest.supported_features},
            },
            "objective": {"type": "string"},
            "requirements": {"type": "array", "items": {"type": "string"}},
            "user_prompt": {"type": "string"},
        },
    }
