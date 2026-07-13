"""Closed-grammar nested component and spatial-constraint evaluation."""

from __future__ import annotations

import operator
from typing import Any

from intentforge.assemblies.schema import (
    AssemblyChildObservation,
    AssemblyConstraintObservation,
    AssemblyEvaluationReport,
    AssemblyManifest,
)
from intentforge.schemas import ParameterTable, ValidationReport
from intentforge.topology.expressions import evaluate_numeric_expression

_COMPARATORS = {
    "lt": operator.lt,
    "le": operator.le,
    "eq": operator.eq,
    "ge": operator.ge,
    "gt": operator.gt,
}


def _bound_value(reference: str, tables: dict[str, ParameterTable]) -> Any:
    component_id, parameter_name = reference.split(".", 1)
    return tables[component_id].get(parameter_name).value


def resolve_component_quantities(manifest: AssemblyManifest, tables: dict[str, ParameterTable]) -> dict[str, int]:
    quantities: dict[str, int] = {}
    for component in manifest.components:
        if component.quantity is not None:
            quantities[component.component_id] = component.quantity
            continue
        variables = {name: _bound_value(reference, tables) for name, reference in component.quantity_bindings.items()}
        value = evaluate_numeric_expression(component.quantity_expression or "", variables)
        if not value.is_integer() or value < 1:
            raise ValueError(f"component quantity must resolve to a positive integer: {component.component_id}")
        quantities[component.component_id] = int(value)
    return quantities


def evaluate_assembly(
    manifest: AssemblyManifest,
    tables: dict[str, ParameterTable],
    child_validations: dict[str, list[ValidationReport]],
) -> AssemblyEvaluationReport:
    """Validate every child before evaluating any assembly-level constraint."""

    quantities = resolve_component_quantities(manifest, tables)
    children: list[AssemblyChildObservation] = []
    for component in manifest.components:
        reports = child_validations.get(component.component_id, [])
        if len(reports) != quantities[component.component_id]:
            raise ValueError(f"child validation count mismatch: {component.component_id}")
        for index, report in enumerate(reports, start=1):
            children.append(AssemblyChildObservation(
                instance_id=f"{component.component_id}_{index:03d}",
                component_id=component.component_id,
                topology_family=component.topology_family,
                validation_passed=report.valid,
                validation_report=report.model_dump(mode="json"),
            ))
    nested_passed = all(item.validation_passed for item in children)
    constraints: list[AssemblyConstraintObservation] = []
    for definition in manifest.spatial_constraints:
        if not nested_passed:
            constraints.append(AssemblyConstraintObservation(
                constraint_id=definition.constraint_id,
                status="not_run",
                blocking=definition.blocking,
                operator=definition.operator,
                description=definition.description,
            ))
            continue
        variables = {name: _bound_value(reference, tables) for name, reference in definition.variable_bindings.items()}
        left = evaluate_numeric_expression(definition.left_expression, variables)
        right = evaluate_numeric_expression(definition.right_expression, variables)
        passed = bool(_COMPARATORS[definition.operator](left, right))
        constraints.append(AssemblyConstraintObservation(
            constraint_id=definition.constraint_id,
            status="pass" if passed else "fail",
            blocking=definition.blocking,
            left_value=left,
            operator=definition.operator,
            right_value=right,
            description=definition.description,
        ))
    passed = nested_passed and all(item.status == "pass" or not item.blocking for item in constraints)
    return AssemblyEvaluationReport(
        assembly_family=manifest.assembly_family,
        manifest_version=manifest.manifest_version,
        child_observations=children,
        constraint_observations=constraints,
        nested_validation_passed=nested_passed,
        passed=passed,
        limitations=manifest.limitations,
    )
