"""Deterministic evaluator for engineering knowledge rules."""

from __future__ import annotations

import ast
import operator
from typing import Any

from intentforge.features import feature_flags_for_parameter_table, is_feature_active
from intentforge.knowledge.rules import RuleRegistry
from intentforge.knowledge.schema import DesignKnowledgeRule, KnowledgeFinding
from intentforge.schemas import FeaturePlan, IntentSpec, ParameterTable


_ARITHMETIC_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

_COMPARISON_OPERATORS = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}


class KnowledgeEvaluationError(ValueError):
    """Raised when a declarative rule cannot be safely evaluated."""


def _parameter_value(table: ParameterTable, name: str, default: Any = None) -> Any:
    try:
        return table.get(name).value
    except KeyError:
        return default


def _numeric(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _feature_plan_step_count(feature_plan: FeaturePlan | None) -> int:
    return len(feature_plan.steps) if feature_plan is not None else 0


def _min_positive(values: list[float | None], default: float = 0.0) -> float:
    positives = [value for value in values if value is not None and value > 0]
    return min(positives) if positives else default


def build_design_metrics(parameter_table: ParameterTable, feature_plan: FeaturePlan | None = None) -> dict[str, Any]:
    """Build deterministic engineering metrics used by knowledge rules."""

    flags = feature_flags_for_parameter_table(parameter_table)
    active_optional_feature_count = sum(1 for name in flags if is_feature_active(flags, name))
    family = parameter_table.family
    metrics: dict[str, Any] = {
        "object_type": family,
        "family": family,
        "feature_plan_step_count": _feature_plan_step_count(feature_plan),
        "active_optional_feature_count": active_optional_feature_count,
    }

    if family == "wall_mounted_bracket":
        width = _numeric(_parameter_value(parameter_table, "back_plate_width_mm"))
        height = _numeric(_parameter_value(parameter_table, "back_plate_height_mm"))
        thickness = _numeric(_parameter_value(parameter_table, "back_plate_thickness_mm"))
        hole_diameter = _numeric(_parameter_value(parameter_table, "mounting_hole_diameter_mm"))
        hole_count = _numeric(_parameter_value(parameter_table, "mounting_hole_count"))
        spacing = _numeric(
            _parameter_value(
                parameter_table,
                "mounting_hole_spacing_x_mm",
                _parameter_value(parameter_table, "mounting_hole_spacing_mm", 0.0),
            )
        )
        spacing_y = _numeric(_parameter_value(parameter_table, "mounting_hole_spacing_y_mm", 0.0))
        holes_active = is_feature_active(flags, "mounting_holes") and hole_count > 0
        center_cutout_active = is_feature_active(flags, "center_cutout")
        rounded_corners_active = is_feature_active(flags, "rounded_corners")
        corner_radius = _numeric(_parameter_value(parameter_table, "corner_radius_mm"))
        cutout_width = _numeric(_parameter_value(parameter_table, "center_cutout_width_mm"))
        cutout_height = _numeric(_parameter_value(parameter_table, "center_cutout_height_mm"))

        if holes_active and hole_count >= 4:
            x_edge = width / 2 - spacing / 2 - hole_diameter / 2
            y_edge = height / 2 - spacing_y / 2 - hole_diameter / 2
            hole_edge_distance = min(x_edge, y_edge)
            hole_spacing = min(spacing, spacing_y) if spacing_y else spacing
        elif holes_active:
            hole_edge_distance = width / 2 - spacing / 2 - hole_diameter / 2
            hole_spacing = spacing
        else:
            hole_edge_distance = 0.0
            hole_spacing = 0.0

        cutout_area_ratio = (cutout_width * cutout_height / (width * height)) if width > 0 and height > 0 and center_cutout_active else 0.0
        cutout_web = min((width - cutout_width) / 2, (height - cutout_height) / 2) if center_cutout_active else min(width, height)
        tool_clearance = _min_positive(
            [
                hole_diameter if holes_active else None,
                min(cutout_width, cutout_height) if center_cutout_active else None,
                width,
                height,
            ]
        )

        metrics.update(
            {
                "width": width,
                "height": height,
                "thickness": thickness,
                "hole_count": hole_count,
                "hole_diameter": hole_diameter,
                "hole_spacing": hole_spacing,
                "hole_edge_distance": hole_edge_distance,
                "fastener_edge_clearance": hole_edge_distance,
                "mounting_holes_active": holes_active,
                "center_cutout_active": center_cutout_active,
                "rounded_corners_active": rounded_corners_active,
                "corner_radius": corner_radius,
                "cutout_area_ratio": cutout_area_ratio,
                "minimum_section_thickness": cutout_web,
                "tool_clearance": tool_clearance,
                "bracket_width": width,
                "gusset_enabled": False,
                "vertical_leg_height_to_thickness": 0.0,
            }
        )
        return metrics

    base_length = _numeric(_parameter_value(parameter_table, "base_leg_length_mm"))
    vertical_length = _numeric(_parameter_value(parameter_table, "vertical_leg_length_mm"))
    bracket_width = _numeric(_parameter_value(parameter_table, "bracket_width_mm"))
    thickness = _numeric(_parameter_value(parameter_table, "thickness_mm"))
    hole_diameter = _numeric(_parameter_value(parameter_table, "hole_diameter_mm"))
    base_count = _numeric(_parameter_value(parameter_table, "base_hole_count"))
    vertical_count = _numeric(_parameter_value(parameter_table, "vertical_hole_count"))
    base_spacing = _numeric(_parameter_value(parameter_table, "base_hole_spacing_mm"))
    vertical_spacing = _numeric(_parameter_value(parameter_table, "vertical_hole_spacing_mm"))
    base_active = is_feature_active(flags, "base_mounting_holes") and base_count > 0
    vertical_active = is_feature_active(flags, "vertical_mounting_holes") and vertical_count > 0
    holes_active = base_active or vertical_active
    edge_distances = []
    spacings = []
    if base_active:
        edge_distances.append(min(base_length / 2 - base_spacing / 2 - hole_diameter / 2, bracket_width / 2 - hole_diameter / 2))
        spacings.append(base_spacing)
    if vertical_active:
        edge_distances.append(min(vertical_length / 2 - vertical_spacing / 2 - hole_diameter / 2, bracket_width / 2 - hole_diameter / 2))
        spacings.append(vertical_spacing)

    metrics.update(
        {
            "base_leg_length": base_length,
            "vertical_leg_length": vertical_length,
            "bracket_width": bracket_width,
            "thickness": thickness,
            "hole_count": base_count + vertical_count,
            "hole_diameter": hole_diameter,
            "hole_spacing": min(spacings) if spacings else 0.0,
            "hole_edge_distance": min(edge_distances) if edge_distances else 0.0,
            "fastener_edge_clearance": min(edge_distances) if edge_distances else 0.0,
            "mounting_holes_active": holes_active,
            "base_mounting_holes_active": base_active,
            "vertical_mounting_holes_active": vertical_active,
            "gusset_enabled": is_feature_active(flags, "triangular_gusset") or bool(_parameter_value(parameter_table, "gusset_enabled", False)),
            "vertical_leg_height_to_thickness": vertical_length / thickness if thickness > 0 else 0.0,
            "minimum_section_thickness": min(bracket_width, base_length, vertical_length),
            "tool_clearance": _min_positive([hole_diameter if holes_active else None, bracket_width, thickness]),
            "corner_radius": _numeric(_parameter_value(parameter_table, "outside_edge_fillet_radius_mm", _parameter_value(parameter_table, "inside_fillet_radius_mm", 0.0))),
            "rounded_corners_active": is_feature_active(flags, "outside_edge_fillets") or is_feature_active(flags, "inside_fillet"),
            "center_cutout_active": False,
            "cutout_area_ratio": 0.0,
        }
    )
    return metrics


def _eval_expression_node(node: ast.AST, metrics: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_expression_node(node.body, metrics)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id == "true":
            return True
        if node.id == "false":
            return False
        if node.id not in metrics:
            raise KnowledgeEvaluationError(f"missing metric: {node.id}")
        return metrics[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_expression_node(node.operand, metrics)
    if isinstance(node, ast.BinOp) and type(node.op) in _ARITHMETIC_OPERATORS:
        return _ARITHMETIC_OPERATORS[type(node.op)](
            _eval_expression_node(node.left, metrics),
            _eval_expression_node(node.right, metrics),
        )
    if isinstance(node, ast.BoolOp):
        values = [_eval_expression_node(value, metrics) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(bool(value) for value in values)
        if isinstance(node.op, ast.Or):
            return any(bool(value) for value in values)
    if isinstance(node, ast.Compare):
        left = _eval_expression_node(node.left, metrics)
        for operator_node, comparator in zip(node.ops, node.comparators, strict=True):
            if type(operator_node) not in _COMPARISON_OPERATORS:
                raise KnowledgeEvaluationError("unsupported comparison operator")
            right = _eval_expression_node(comparator, metrics)
            if not _COMPARISON_OPERATORS[type(operator_node)](left, right):
                return False
            left = right
        return True
    raise KnowledgeEvaluationError(f"unsupported expression element: {node.__class__.__name__}")


def evaluate_expression(expression: str, metrics: dict[str, Any]) -> bool:
    """Evaluate a restricted rule expression without executing arbitrary Python."""

    parsed = ast.parse(expression, mode="eval")
    return bool(_eval_expression_node(parsed, metrics))


def _condition_applies(condition: dict[str, Any], metrics: dict[str, Any]) -> bool:
    when = condition.get("when")
    if not when:
        return True
    if not isinstance(when, dict):
        raise KnowledgeEvaluationError("condition.when must be a mapping")
    for key, expected in when.items():
        if metrics.get(key) != expected:
            return False
    return True


def _intent_family(intent: IntentSpec | dict[str, Any] | str) -> str:
    if isinstance(intent, str):
        return intent
    if isinstance(intent, dict):
        return str(intent.get("family") or intent.get("object_type") or "")
    return intent.family


def evaluate_design(
    intent: IntentSpec | dict[str, Any] | str,
    metrics: dict[str, Any],
    rules: list[DesignKnowledgeRule] | None = None,
) -> list[KnowledgeFinding]:
    """Evaluate applicable design knowledge rules against deterministic metrics."""

    family = _intent_family(intent)
    findings: list[KnowledgeFinding] = []
    if rules is None:
        registry = RuleRegistry.load()
        selected_rules = registry.rules
        rule_sources = registry.rule_sources()
    else:
        selected_rules = rules
        rule_sources = {}
    for rule in selected_rules:
        if family not in rule.applies_to:
            continue
        if rule.status != "active":
            continue
        metadata: dict[str, Any] = {
            "expression": rule.condition["expression"],
            "rule_version": rule.rule_version,
            "rule_status": rule.status,
            "source_reference": rule.source_reference,
            "created_by": rule.created_by,
            "last_updated": rule.last_updated,
            "metrics": {key: metrics.get(key) for key in rule.condition.get("required_metrics", [])},
        }
        source = rule_sources.get(rule.id)
        if source:
            metadata.update(
                {
                    "pack_id": source.get("pack_id"),
                    "pack_version": source.get("pack_version"),
                    "pack_category": source.get("category"),
                    "pack_source": source.get("source"),
                }
            )
        try:
            if not _condition_applies(rule.condition, metrics):
                continue
            passed = evaluate_expression(rule.condition["expression"], metrics)
            message = f"{rule.name} passed." if passed else rule.description
        except (KnowledgeEvaluationError, SyntaxError, ZeroDivisionError, TypeError) as exc:
            passed = False
            message = f"Knowledge rule could not be evaluated: {exc}"
            metadata["evaluation_error"] = str(exc)
        findings.append(
            KnowledgeFinding(
                rule_id=rule.id,
                rule_name=rule.name,
                category=rule.category,
                severity=rule.severity,
                passed=passed,
                message=message,
                recommendation=rule.recommendation,
                confidence=rule.confidence,
                metadata=metadata,
            )
        )
    return findings


def evaluate_parameter_table(
    parameter_table: ParameterTable,
    feature_plan: FeaturePlan | None = None,
    rules: list[DesignKnowledgeRule] | None = None,
) -> list[KnowledgeFinding]:
    """Evaluate engineering knowledge rules for a parameter table."""

    return evaluate_design(parameter_table.family, build_design_metrics(parameter_table, feature_plan), rules)
