"""Algebraic inversion of declarative knowledge rule expressions.

Phase 30 of IntentForge introduces a deterministic auto-remediation engine
that consumes a rejected parameter table, evaluates each failed knowledge
rule condition, and mathematically inverts the condition to derive the
nearest compliant boundary state. The engine is restricted to a closed
grammar derived from the YAML rule definitions and never invokes dynamic
code paths, ``eval``/``exec``, or external models.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any


_REMEDIATION_ENGINE_VERSION = "1.0"
REMEDIATION_ENGINE_VERSION = _REMEDIATION_ENGINE_VERSION

# Closed grammar we recognize for declarative remediation. These are the
# minimal operators observed in the shipped rule packs:
#   * arithmetic: Add, Sub, Mult, Div (with USub on literals)
#   * comparisons: Gt, GtE, Lt, LtE, Eq, NotEq
#   * boolean: And, Or (treated as conjunctions of separate comparisons)
#   * boolean literals: ``true`` and ``false``
#   * metric names: bare identifiers
_ARITH_OPS = {ast.Add, ast.Sub, ast.Mult, ast.Div}
_CMP_OPS = {ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq}


class RemediationAlgebraError(ValueError):
    """Raised when an expression cannot be algebraically inverted."""


@dataclass(frozen=True)
class BoundaryTerm:
    """A single term in a normalized rule inequality."""

    metric: str | None
    coefficient: float

    def evaluate(self, metrics: dict[str, float]) -> float:
        if self.metric is None:
            return self.coefficient
        return self.coefficient * float(metrics.get(self.metric, 0.0))

    def depends_on(self, metric: str) -> bool:
        return self.metric == metric


@dataclass(frozen=True)
class NormalizedInequality:
    """Normalize a rule expression into a linear inequality of one side."""

    metric: str | None
    terms: tuple[BoundaryTerm, ...]
    comparison: str  # one of ">=", ">", "<=", "<", "==", "!="
    constant: float
    inverted: bool = False  # True if the subject was originally on the right

    def expression(self) -> str:
        rendered_terms: list[str] = []
        for index, term in enumerate(self.terms):
            rendered_parts: list[str] = []
            if term.coefficient < 0:
                rendered_parts.append("-")
                coefficient = abs(term.coefficient)
            else:
                coefficient = term.coefficient
            if index > 0:
                if term.coefficient >= 0:
                    rendered_parts.append(" + ")
                else:
                    rendered_parts.append(" ")
            if term.metric is None:
                rendered_parts.append(f"{coefficient:g}")
            else:
                if coefficient == 1.0:
                    rendered_parts.append(term.metric)
                else:
                    rendered_parts.append(f"{coefficient:g} * {term.metric}")
            rendered_terms.append("".join(rendered_parts))
        return " ".join(rendered_terms) + f" {self.comparison} {self.constant:g}"


@dataclass(frozen=True)
class RemediationAction:
    """One concrete parameter change suggested by the inversion engine."""

    parameter: str
    current_value: float
    proposed_value: float
    metric: str
    rule_id: str
    rationale: str
    delta: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "current_value": self.current_value,
            "proposed_value": self.proposed_value,
            "metric": self.metric,
            "rule_id": self.rule_id,
            "rationale": self.rationale,
            "delta": self.delta,
        }


@dataclass(frozen=True)
class RemediationPlan:
    """A deterministic remediation plan for one rule."""

    rule_id: str
    rule_name: str
    status: str  # "remediation_synthesized" or "remediation_impossible"
    boundary_inequality: str
    inequality_metric: str | None
    actions: tuple[RemediationAction, ...] = ()
    rationale: str = ""
    fallback_advice: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "status": self.status,
            "boundary_inequality": self.boundary_inequality,
            "inequality_metric": self.inequality_metric,
            "actions": [action.to_dict() for action in self.actions],
            "rationale": self.rationale,
            "fallback_advice": self.fallback_advice,
        }


@dataclass(frozen=True)
class RemediationDelta:
    """A complete remediation delta covering one or more rules."""

    remediation_id: str
    remediation_status: str  # "remediation_synthesized" or "remediation_impossible"
    target_family: str
    source_metrics: dict[str, float]
    proposed_parameters: dict[str, float]
    parameter_changes: tuple[RemediationAction, ...]
    plans: tuple[RemediationPlan, ...]
    iteration_count: int
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "remediation_id": self.remediation_id,
            "remediation_status": self.remediation_status,
            "target_family": self.target_family,
            "source_metrics": dict(sorted(self.source_metrics.items())),
            "proposed_parameters": dict(sorted(self.proposed_parameters.items())),
            "parameter_changes": [action.to_dict() for action in self.parameter_changes],
            "plans": [plan.to_dict() for plan in self.plans],
            "iteration_count": self.iteration_count,
            "remediation_engine_version": _REMEDIATION_ENGINE_VERSION,
            "rationale": self.rationale,
        }


def _eval_literal(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    raise RemediationAlgebraError(f"unsupported literal expression: {ast.dump(node)}")


def _walk_terms(node: ast.AST, sign: float = 1.0) -> tuple[list[BoundaryTerm], float]:
    """Walk a side of a comparison, returning terms and a constant offset."""

    if isinstance(node, ast.BinOp) and type(node.op) in _ARITH_OPS:
        if isinstance(node.op, ast.Sub):
            left_terms, left_const = _walk_terms(node.left, sign)
            right_terms, right_const = _walk_terms(node.right, -sign)
            return left_terms + right_terms, left_const + right_const
        if isinstance(node.op, ast.Add):
            left_terms, left_const = _walk_terms(node.left, sign)
            right_terms, right_const = _walk_terms(node.right, sign)
            return left_terms + right_terms, left_const + right_const
        if isinstance(node.op, ast.Mult):
            return _resolve_multiplication(node.left, node.right, sign)
        if isinstance(node.op, ast.Div):
            return _resolve_division(node.left, node.right, sign)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        sub_terms, sub_const = _walk_terms(node.operand, -sign)
        return sub_terms, sub_const
    if isinstance(node, ast.Name):
        return [BoundaryTerm(metric=node.id, coefficient=sign)], 0.0
    if isinstance(node, ast.Constant):
        value = _eval_literal(node)
        return [], sign * value
    raise RemediationAlgebraError(f"unsupported expression node: {ast.dump(node)}")


def _resolve_multiplication(left: ast.AST, right: ast.AST, sign: float) -> tuple[list[BoundaryTerm], float]:
    left_value = _try_eval_const(left)
    if left_value is not None:
        terms, const = _walk_terms(right, sign * left_value)
        return terms, const
    right_value = _try_eval_const(right)
    if right_value is not None:
        terms, const = _walk_terms(left, sign * right_value)
        return terms, const
    raise RemediationAlgebraError("non-linear multiplication is not supported by the remediation engine")


def _resolve_division(left: ast.AST, right: ast.AST, sign: float) -> tuple[list[BoundaryTerm], float]:
    right_value = _try_eval_const(right)
    if right_value is None or right_value == 0:
        raise RemediationAlgebraError("division by non-constant or zero is not supported")
    terms, const = _walk_terms(left, sign / right_value)
    return terms, const


def _try_eval_const(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _try_eval_const(node.operand)
        if inner is not None:
            return -inner
    return None


def _cmp_operator(node: ast.cmpop) -> str:
    if isinstance(node, ast.Gt):
        return ">"
    if isinstance(node, ast.GtE):
        return ">="
    if isinstance(node, ast.Lt):
        return "<"
    if isinstance(node, ast.LtE):
        return "<="
    if isinstance(node, ast.Eq):
        return "=="
    if isinstance(node, ast.NotEq):
        return "!="
    raise RemediationAlgebraError(f"unsupported comparison operator: {type(node).__name__}")


def normalize_inequality(expression: str) -> NormalizedInequality:
    """Parse a single comparison expression into a normalized linear inequality.

    The normalized form is::

        sum(coef_i * metric_i) <op> constant

    with at most one metric that has a non-zero coefficient on the left. This
    permits closed-form algebraic inversion.
    """

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise RemediationAlgebraError(f"invalid expression syntax: {exc}") from exc
    body = tree.body
    if isinstance(body, ast.BoolOp):
        raise RemediationAlgebraError("compound boolean expressions must be split per comparison")
    if not isinstance(body, ast.Compare) or len(body.ops) != 1 or len(body.comparators) != 1:
        raise RemediationAlgebraError("expression must contain exactly one comparison")
    op_node = body.ops[0]
    comparison = _cmp_operator(op_node)
    left_terms, left_const = _walk_terms(body.left, 1.0)
    right_terms, right_const = _walk_terms(body.comparators[0], 1.0)
    net_terms = left_terms + [
        BoundaryTerm(metric=term.metric, coefficient=-term.coefficient) for term in right_terms
    ]
    net_const = left_const - right_const
    return NormalizedInequality(
        metric=net_terms[0].metric if net_terms else None,
        terms=tuple(net_terms),
        comparison=comparison,
        constant=net_const,
    )


def extract_metric_to_parameter_map(
    parameter_table: dict[str, Any] | Any,
    *,
    family: str,
) -> dict[str, str]:
    """Map each engineering metric used by rule expressions back to the
    parameter that controls it.

    The mapping is curated per CAD family from the deterministic metrics
    builder in :mod:`intentforge.knowledge.evaluator`. The keys are metric
    names (the same names used by the rule expressions) and the values are
    parameter table field names.
    """

    if family == "wall_mounted_bracket":
        return {
            "width": "back_plate_width_mm",
            "height": "back_plate_height_mm",
            "thickness": "back_plate_thickness_mm",
            "hole_diameter": "mounting_hole_diameter_mm",
            "hole_spacing": "mounting_hole_spacing_x_mm",
            "hole_edge_distance": "back_plate_width_mm",
            "corner_radius": "corner_radius_mm",
            "cutout_area_ratio": "center_cutout_width_mm",
        }
    if family == "l_bracket":
        return {
            "base_leg_length": "base_leg_length_mm",
            "vertical_leg_length": "vertical_leg_length_mm",
            "bracket_width": "bracket_width_mm",
            "thickness": "thickness_mm",
            "hole_diameter": "hole_diameter_mm",
            "hole_spacing": "base_hole_spacing_mm",
            "hole_edge_distance": "bracket_width_mm",
            "fastener_edge_clearance": "bracket_width_mm",
            "corner_radius": "outside_edge_fillet_radius_mm",
            "vertical_leg_height_to_thickness": "vertical_leg_length_mm",
            "gusset_enabled": "gusset_enabled",
            "minimum_section_thickness": "bracket_width_mm",
            "tool_clearance": "bracket_width_mm",
            "active_optional_feature_count": "feature_flags",
        }
    try:
        from intentforge.topology.registry import get_topology_registry

        manifest = get_topology_registry().get(family)
    except (ImportError, ValueError) as exc:
        raise RemediationAlgebraError(f"unsupported CAD family: {family}") from exc
    return {
        mapping.metric: mapping.remediation_parameter
        for mapping in manifest.capability_evidence_binding.rule_variable_mapping
    }


def metric_to_parameter_transform(
    *,
    family: str,
    metric: str,
    target_metric_value: float,
    parameters: dict[str, Any],
) -> float:
    """Translate a target metric value into the corresponding parameter value.

    The wall-mounted and L-bracket metric definitions have a small set of
    affine mappings between a metric and its controlling parameter. We
    implement those mappings explicitly here so the inversion produces a
    concrete parameter value rather than a metric value.
    """

    if family == "wall_mounted_bracket":
        spacing = _coerce_float(parameters.get("mounting_hole_spacing_x_mm"))
        spacing_y = _coerce_float(parameters.get("mounting_hole_spacing_y_mm"))
        spacing_axis = spacing_y or spacing
        hole_diameter = _coerce_float(parameters.get("mounting_hole_diameter_mm"))
        if metric == "hole_edge_distance":
            return 2 * target_metric_value + spacing_axis + hole_diameter
        if metric == "hole_spacing":
            return target_metric_value
        if metric == "bracket_width":
            return target_metric_value
        if metric == "width":
            return target_metric_value
        if metric == "height":
            return target_metric_value
        if metric == "thickness":
            return target_metric_value
        if metric == "hole_diameter":
            return target_metric_value
        if metric == "corner_radius":
            return target_metric_value
        if metric == "cutout_area_ratio":
            height = _coerce_float(parameters.get("back_plate_height_mm"))
            width = _coerce_float(parameters.get("back_plate_width_mm"))
            cutout_height = _coerce_float(parameters.get("center_cutout_height_mm"))
            target_area = target_metric_value * width * height
            if cutout_height <= 0:
                return target_metric_value
            return target_area / cutout_height
    if family == "l_bracket":
        hole_diameter = _coerce_float(parameters.get("hole_diameter_mm"))
        spacing = _coerce_float(parameters.get("base_hole_spacing_mm"))
        if metric == "hole_edge_distance":
            return 2 * target_metric_value + spacing + hole_diameter
        if metric == "bracket_width":
            return target_metric_value
        if metric == "thickness":
            return target_metric_value
        if metric == "base_leg_length":
            return target_metric_value
        if metric == "vertical_leg_length":
            return target_metric_value
        if metric == "hole_spacing":
            return target_metric_value
        if metric == "hole_diameter":
            return target_metric_value
        if metric == "corner_radius":
            return target_metric_value
        if metric == "vertical_leg_height_to_thickness":
            thickness = _coerce_float(parameters.get("thickness_mm"))
            return target_metric_value * thickness
        if metric == "minimum_section_thickness":
            return target_metric_value
        if metric == "tool_clearance":
            return target_metric_value
        if metric == "fastener_edge_clearance":
            return 2 * target_metric_value + spacing + hole_diameter
    try:
        from intentforge.topology.expressions import solve_parameter_for_metric
        from intentforge.topology.registry import get_topology_registry

        manifest = get_topology_registry().get(family)
        mapping = manifest.metric_mapping(metric)
        definition = manifest.parameter(mapping.remediation_parameter)
        if definition.safe_bounds is None:
            raise RemediationAlgebraError(
                f"remediation parameter has no safe bounds: {mapping.remediation_parameter}"
            )
        return solve_parameter_for_metric(
            mapping.expression,
            target_metric_value=target_metric_value,
            parameter_name=mapping.remediation_parameter,
            parameters=parameters,
            safe_bounds=definition.safe_bounds,
        )
    except (ImportError, KeyError, ValueError) as exc:
        raise RemediationAlgebraError(f"unsupported metric-to-parameter transform: {family}.{metric}") from exc


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parameter_numeric_value(parameters: dict[str, Any], name: str) -> float:
    if name not in parameters:
        raise RemediationAlgebraError(f"missing parameter: {name}")
    value = parameters[name]
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    raise RemediationAlgebraError(f"parameter {name} is not numeric: {value!r}")


def _solve_boundary(
    inequality: NormalizedInequality,
    *,
    metric: str,
    other_metrics: dict[str, float],
    parameter_value: float,
) -> float:
    """Solve the linear inequality for the given metric.

    The inequality is in the normalized form::

        sum(coef_i * metric_i) <op> constant

    with the constant on the right-hand side. We isolate the target metric
    by evaluating every other term against the supplied metric dictionary
    and folding the result back into the right-hand side. This produces the
    smallest parameter change that satisfies the inequality.
    """

    rhs_constant = inequality.constant
    coef_a = 0.0
    for term in inequality.terms:
        if term.metric == metric:
            coef_a += term.coefficient
        elif term.metric is None:
            rhs_constant -= term.coefficient
        else:
            rhs_constant -= term.coefficient * float(other_metrics.get(term.metric, 0.0))
    if coef_a == 0:
        raise RemediationAlgebraError(
            f"metric {metric} does not appear in inequality for {inequality.metric}"
        )
    rhs_value = rhs_constant / coef_a
    comparison = inequality.comparison
    if comparison == ">=":
        target = rhs_value
    elif comparison == ">":
        target = rhs_value + (0.001 / coef_a if coef_a > 0 else -0.001 / abs(coef_a))
    elif comparison == "<=":
        target = rhs_value
    elif comparison == "<":
        target = rhs_value - (0.001 / abs(coef_a))
    elif comparison == "==":
        target = rhs_value
    elif comparison == "!=":
        raise RemediationAlgebraError("cannot satisfy an inequality that demands inequality")
    else:
        raise RemediationAlgebraError(f"unsupported comparison operator: {comparison}")
    if comparison in {">=", ">"} and coef_a > 0 and target < parameter_value:
        target = parameter_value
    if comparison in {"<=", "<"} and coef_a > 0 and target > parameter_value:
        target = parameter_value
    return target


def _other_metric_terms(
    inequality: NormalizedInequality,
    target_metric: str,
) -> dict[str, float]:
    """Project inequality terms other than the target metric into constants."""

    return {
        term.metric: term.coefficient
        for term in inequality.terms
        if term.metric is not None and term.metric != target_metric
    }


def synthesize_remediation(
    *,
    family: str,
    parameters: dict[str, Any],
    metrics: dict[str, float],
    failed_findings: list[dict[str, Any]],
    rule_registry: dict[str, dict[str, Any]],
) -> RemediationDelta:
    """Compute a deterministic remediation delta for the given failure list.

    Each failure describes a single knowledge rule whose expression evaluated
    to False. The remediation engine normalizes the rule's expression into a
    linear inequality, identifies which parameter(s) control the failing
    metric, and inverts the inequality to produce the smallest parameter
    change that flips the evaluation to True.
    """

    metric_to_parameter = extract_metric_to_parameter_map(parameters, family=family)
    plans: list[RemediationPlan] = []
    proposed_parameters: dict[str, float] = {
        name: _parameter_numeric_value(parameters, name) if isinstance(parameters.get(name), (int, float))
        else (1.0 if parameters.get(name) is True else 0.0 if parameters.get(name) is False else 0.0)
        for name in metric_to_parameter.values()
        if name in parameters
    }
    actions: list[RemediationAction] = []
    impossible_reasons: list[str] = []
    iteration_count = 0
    for finding in failed_findings:
        iteration_count += 1
        rule_id = finding.get("rule_id")
        if not rule_id or rule_id not in rule_registry:
            plans.append(RemediationPlan(
                rule_id=rule_id or "unknown",
                rule_name=finding.get("rule_name", "unknown"),
                status="remediation_impossible",
                boundary_inequality="",
                inequality_metric=None,
                fallback_advice="Rule registry does not contain an entry for this finding.",
            ))
            continue
        rule = rule_registry[rule_id]
        expression = rule.get("condition", {}).get("expression")
        if not isinstance(expression, str):
            plans.append(RemediationPlan(
                rule_id=rule_id,
                rule_name=rule.get("name", rule_id),
                status="remediation_impossible",
                boundary_inequality="",
                inequality_metric=None,
                fallback_advice="Rule has no declarative expression.",
            ))
            continue
        try:
            inequality = normalize_inequality(expression)
        except RemediationAlgebraError as exc:
            plans.append(RemediationPlan(
                rule_id=rule_id,
                rule_name=rule.get("name", rule_id),
                status="remediation_impossible",
                boundary_inequality=expression,
                inequality_metric=None,
                fallback_advice=f"Expression is outside the remediation engine grammar: {exc}",
            ))
            continue
        if not inequality.metric:
            plans.append(RemediationPlan(
                rule_id=rule_id,
                rule_name=rule.get("name", rule_id),
                status="remediation_impossible",
                boundary_inequality=inequality.expression(),
                inequality_metric=None,
                fallback_advice="Inequality does not depend on a recoverable metric.",
            ))
            continue
        metric = inequality.metric
        parameter_name = metric_to_parameter.get(metric)
        if parameter_name is None or parameter_name not in parameters:
            plans.append(RemediationPlan(
                rule_id=rule_id,
                rule_name=rule.get("name", rule_id),
                status="remediation_impossible",
                boundary_inequality=inequality.expression(),
                inequality_metric=metric,
                fallback_advice=f"No parameter is mapped to metric {metric}.",
            ))
            continue
        current_value = _parameter_numeric_value(parameters, parameter_name)
        try:
            metric_target = _solve_boundary(
                inequality,
                metric=metric,
                other_metrics=metrics,
                parameter_value=float(metrics.get(metric, current_value)),
            )
            target_value = metric_to_parameter_transform(
                family=family,
                metric=metric,
                target_metric_value=metric_target,
                parameters=parameters,
            )
        except RemediationAlgebraError as exc:
            plans.append(RemediationPlan(
                rule_id=rule_id,
                rule_name=rule.get("name", rule_id),
                status="remediation_impossible",
                boundary_inequality=inequality.expression(),
                inequality_metric=metric,
                fallback_advice=str(exc),
            ))
            continue
        delta = round(target_value - current_value, 6)
        if delta == 0:
            plans.append(RemediationPlan(
                rule_id=rule_id,
                rule_name=rule.get("name", rule_id),
                status="remediation_synthesized",
                boundary_inequality=inequality.expression(),
                inequality_metric=metric,
                actions=(),
                rationale="Parameter is already on the correct side of the boundary.",
            ))
            continue
        action = RemediationAction(
            parameter=parameter_name,
            current_value=current_value,
            proposed_value=round(target_value, 6),
            metric=metric,
            rule_id=rule_id,
            rationale=(
                f"Invert {rule.get('name', rule_id)} boundary: "
                f"{inequality.expression()} for metric {metric}."
            ),
            delta=delta,
        )
        actions.append(action)
        proposed_parameters[parameter_name] = round(target_value, 6)
        plans.append(RemediationPlan(
            rule_id=rule_id,
            rule_name=rule.get("name", rule_id),
            status="remediation_synthesized",
            boundary_inequality=inequality.expression(),
            inequality_metric=metric,
            actions=(action,),
            rationale=action.rationale,
        ))
    if not plans:
        overall_status = "remediation_synthesized"
    elif all(plan.status == "remediation_impossible" for plan in plans):
        overall_status = "remediation_impossible"
    else:
        overall_status = "remediation_synthesized"
    import hashlib
    remediation_id = "rem_" + hashlib.sha256(
        f"{family}|{sorted(proposed_parameters.items())}".encode("utf-8")
    ).hexdigest()[:16]
    rationale_parts = [
        f"Deterministic inversion across {len(plans)} failed rule(s).",
    ]
    rationale_parts.extend(impossible_reasons)
    return RemediationDelta(
        remediation_id=remediation_id,
        remediation_status=overall_status,
        target_family=family,
        source_metrics=dict(sorted(metrics.items())),
        proposed_parameters=dict(sorted(proposed_parameters.items())),
        parameter_changes=tuple(actions),
        plans=tuple(plans),
        iteration_count=iteration_count,
        rationale=" ".join(rationale_parts),
    )


__all__ = [
    "REMEDIATION_ENGINE_VERSION",
    "RemediationAlgebraError",
    "NormalizedInequality",
    "RemediationAction",
    "RemediationDelta",
    "RemediationPlan",
    "BoundaryTerm",
    "extract_metric_to_parameter_map",
    "metric_to_parameter_transform",
    "normalize_inequality",
    "synthesize_remediation",
]
