"""Closed-grammar nested component and spatial-constraint evaluation."""

from __future__ import annotations

import operator
from typing import Any

from intentforge.assemblies.schema import (
    AssemblyChildObservation,
    AssemblyConstraintObservation,
    AssemblyEvaluationReport,
    AssemblyManifest,
    AssemblyRemediationAction,
)
from intentforge.schemas import ParameterTable, ValidationReport
from intentforge.topology.expressions import (
    TopologyExpressionError,
    evaluate_numeric_expression,
    solve_parameter_for_metric,
)
from intentforge.topology.registry import get_topology_registry

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
    *,
    remediation_actions: list[AssemblyRemediationAction] | None = None,
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
        remediation_actions=remediation_actions or [],
        remediation_applied=any(item.status == "applied" for item in remediation_actions or []),
        nested_validation_passed=nested_passed,
        passed=passed,
        limitations=manifest.limitations,
    )


def _target_residual(operator_name: str, margin: float) -> float:
    if operator_name in {"lt", "le"}:
        return -margin
    if operator_name in {"gt", "ge"}:
        return margin
    return 0.0


def remediate_assembly_constraints(
    manifest: AssemblyManifest,
    tables: dict[str, ParameterTable],
    evaluation: AssemblyEvaluationReport,
) -> tuple[dict[str, ParameterTable], list[AssemblyRemediationAction]]:
    """Apply only manifest-authorized cross-component parameter remediations."""

    updated = dict(tables)
    actions: list[AssemblyRemediationAction] = []
    observations = {item.constraint_id: item for item in evaluation.constraint_observations}
    for definition in manifest.spatial_constraints:
        observation = observations.get(definition.constraint_id)
        if observation is None or observation.status != "fail" or not definition.blocking:
            continue
        strategy = definition.remediation
        if strategy is None:
            actions.append(AssemblyRemediationAction(
                constraint_id=definition.constraint_id,
                status="impossible",
                boundary_margin=0.0,
                rationale="No declarative remediation strategy is registered for this constraint.",
            ))
            continue
        target_reference = definition.variable_bindings[strategy.target_variable]
        component_id, parameter_name = target_reference.split(".", 1)
        parameter = updated[component_id].get(parameter_name)
        current = parameter.value
        topology_parameter = get_topology_registry().get(updated[component_id].family).parameter(parameter_name)
        if isinstance(current, bool) or not isinstance(current, int | float) or topology_parameter.safe_bounds is None:
            actions.append(AssemblyRemediationAction(
                constraint_id=definition.constraint_id,
                status="impossible",
                component_id=component_id,
                parameter_name=parameter_name,
                boundary_margin=strategy.boundary_margin,
                rationale="The remediation target is not a bounded numeric component parameter.",
            ))
            continue
        variables = {
            name: _bound_value(reference, updated)
            for name, reference in definition.variable_bindings.items()
        }
        residual_expression = f"({definition.left_expression}) - ({definition.right_expression})"
        try:
            solved = solve_parameter_for_metric(
                residual_expression,
                target_metric_value=_target_residual(definition.operator, strategy.boundary_margin),
                parameter_name=strategy.target_variable,
                parameters=variables,
                safe_bounds=topology_parameter.safe_bounds,
            )
        except TopologyExpressionError as exc:
            actions.append(AssemblyRemediationAction(
                constraint_id=definition.constraint_id,
                status="impossible",
                component_id=component_id,
                parameter_name=parameter_name,
                previous_value=float(current),
                boundary_margin=strategy.boundary_margin,
                rationale=f"Closed-grammar solver could not find a bounded solution: {exc}",
            ))
            continue
        if topology_parameter.parameter_type == "integer":
            solved = float(round(solved))
        direction_valid = (
            strategy.direction == "either"
            or strategy.direction == "increase" and solved > float(current)
            or strategy.direction == "decrease" and solved < float(current)
        )
        if not direction_valid:
            actions.append(AssemblyRemediationAction(
                constraint_id=definition.constraint_id,
                status="impossible",
                component_id=component_id,
                parameter_name=parameter_name,
                previous_value=float(current),
                proposed_value=solved,
                boundary_margin=strategy.boundary_margin,
                rationale="The bounded solution violates the manifest-authorized remediation direction.",
            ))
            continue
        changed_parameters = [
            item.model_copy(update={
                "value": int(solved) if topology_parameter.parameter_type == "integer" else solved,
                "source": "derived",
                "reason": strategy.rationale,
                "metadata": {
                    **item.metadata,
                    "assembly_remediation_constraint": definition.constraint_id,
                },
            }) if item.name == parameter_name else item
            for item in updated[component_id].parameters
        ]
        updated[component_id] = updated[component_id].model_copy(update={"parameters": changed_parameters})
        actions.append(AssemblyRemediationAction(
            constraint_id=definition.constraint_id,
            status="applied",
            component_id=component_id,
            parameter_name=parameter_name,
            previous_value=float(current),
            proposed_value=solved,
            boundary_margin=strategy.boundary_margin,
            rationale=strategy.rationale,
        ))
    return updated, actions


def remediate_invalid_children(
    tables: dict[str, ParameterTable],
    child_validations: dict[str, list[ValidationReport]],
) -> tuple[dict[str, ParameterTable], list[AssemblyRemediationAction]]:
    """Invoke Phase 30 remediation only for components that failed validation."""

    from intentforge.knowledge.evaluator import evaluate_design
    from intentforge.knowledge.rules import RuleRegistry
    from intentforge.remediation.algebra import synthesize_remediation
    from intentforge.remediation.engine import build_metrics

    updated = dict(tables)
    actions: list[AssemblyRemediationAction] = []
    registry = RuleRegistry.load()
    rule_payload = {
        rule.id: rule.model_dump(mode="json")
        for rule in registry.get_active_rules()
    }
    for component_id in sorted(updated):
        reports = child_validations.get(component_id, [])
        if reports and all(report.valid for report in reports):
            continue
        table = updated[component_id]
        parameters = {item.name: item.value for item in table.parameters}
        metrics = build_metrics(parameters, family=table.family)
        findings = [
            finding for finding in evaluate_design(table.family, metrics)
            if not finding.passed
        ]
        failed_findings = [
            {
                "rule_id": finding.rule_id,
                "rule_name": finding.rule_name,
                "severity": finding.severity,
                "metrics": finding.metadata.get("metrics", {}),
            }
            for finding in findings
        ]
        if not failed_findings:
            actions.append(AssemblyRemediationAction(
                constraint_id=f"child_{component_id}_validation",
                action_kind="child_rule",
                status="impossible",
                component_id=component_id,
                boundary_margin=0.0,
                rationale="Child validation failed without a corresponding remediable knowledge finding.",
            ))
            continue
        delta = synthesize_remediation(
            family=table.family,
            parameters=parameters,
            metrics=metrics,
            failed_findings=failed_findings,
            rule_registry=rule_payload,
        )
        candidates: dict[str, list[Any]] = {}
        for candidate in delta.parameter_changes:
            candidates.setdefault(candidate.parameter, []).append(candidate)
        if not candidates:
            actions.append(AssemblyRemediationAction(
                constraint_id=f"child_{component_id}_knowledge",
                action_kind="child_rule",
                status="impossible",
                component_id=component_id,
                rule_ids=sorted({item["rule_id"] for item in failed_findings}),
                boundary_margin=0.0,
                rationale=delta.rationale or "Phase 30 could not synthesize a bounded child remediation.",
            ))
            continue
        proposed: dict[str, tuple[float, list[Any]]] = {}
        for parameter_name, parameter_actions in sorted(candidates.items()):
            current = float(parameters[parameter_name])
            values = [float(item.proposed_value) for item in parameter_actions]
            if all(value >= current for value in values):
                selected = max(values)
            elif all(value <= current for value in values):
                selected = min(values)
            else:
                actions.append(AssemblyRemediationAction(
                    constraint_id=f"child_{component_id}_knowledge",
                    action_kind="child_rule",
                    status="impossible",
                    component_id=component_id,
                    parameter_name=parameter_name,
                    previous_value=current,
                    rule_ids=sorted({item.rule_id for item in parameter_actions}),
                    boundary_margin=0.0,
                    rationale="Child knowledge rules proposed conflicting parameter directions.",
                ))
                continue
            definition = get_topology_registry().get(table.family).parameter(parameter_name)
            if definition.safe_bounds is None or not definition.safe_bounds[0] <= selected <= definition.safe_bounds[1]:
                actions.append(AssemblyRemediationAction(
                    constraint_id=f"child_{component_id}_knowledge",
                    action_kind="child_rule",
                    status="impossible",
                    component_id=component_id,
                    parameter_name=parameter_name,
                    previous_value=current,
                    proposed_value=selected,
                    rule_ids=sorted({item.rule_id for item in parameter_actions}),
                    boundary_margin=0.0,
                    rationale="Child remediation proposal is outside the topology safe bounds.",
                ))
                continue
            proposed[parameter_name] = (selected, parameter_actions)
        if not proposed:
            continue
        changed_parameters = []
        for parameter in table.parameters:
            if parameter.name not in proposed:
                changed_parameters.append(parameter)
                continue
            selected, parameter_actions = proposed[parameter.name]
            definition = get_topology_registry().get(table.family).parameter(parameter.name)
            value: int | float = int(round(selected)) if definition.parameter_type == "integer" else selected
            rule_ids = sorted({item.rule_id for item in parameter_actions})
            changed_parameters.append(parameter.model_copy(update={
                "value": value,
                "source": "derived",
                "reason": "Phase 30 child remediation was triggered by failed component validation.",
                "metadata": {
                    **parameter.metadata,
                    "assembly_child_remediation_rules": rule_ids,
                },
            }))
            actions.append(AssemblyRemediationAction(
                constraint_id=f"child_{component_id}_knowledge",
                action_kind="child_rule",
                status="applied",
                component_id=component_id,
                parameter_name=parameter.name,
                previous_value=float(parameters[parameter.name]),
                proposed_value=float(value),
                rule_ids=rule_ids,
                boundary_margin=0.0,
                rationale="Phase 30 child remediation was triggered by failed component validation.",
            ))
        updated[component_id] = table.model_copy(update={"parameters": changed_parameters})
    return updated, actions
