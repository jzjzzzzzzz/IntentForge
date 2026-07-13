"""Safe arithmetic for declarative topology metric mappings."""

from __future__ import annotations

import ast
import operator
from typing import Any


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


class TopologyExpressionError(ValueError):
    pass


def _evaluate(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, variables)
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise TopologyExpressionError(f"missing variable: {node.id}")
        return float(variables[node.id])
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_evaluate(node.operand, variables)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left = _evaluate(node.left, variables)
        right = _evaluate(node.right, variables)
        if isinstance(node.op, ast.Div) and right == 0:
            raise TopologyExpressionError("division by zero")
        return float(_OPS[type(node.op)](left, right))
    raise TopologyExpressionError(f"unsupported expression element: {node.__class__.__name__}")


def evaluate_numeric_expression(expression: str, variables: dict[str, Any]) -> float:
    """Evaluate the closed arithmetic grammar used by topology manifests."""

    numeric: dict[str, float] = {}
    for key, value in variables.items():
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        numeric[key] = float(value)
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise TopologyExpressionError(f"invalid expression syntax: {exc.msg}") from exc
    return _evaluate(parsed, numeric)


def expression_names(expression: str) -> set[str]:
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise TopologyExpressionError(f"invalid expression syntax: {exc.msg}") from exc
    for node in ast.walk(parsed):
        if isinstance(node, (ast.Call, ast.Attribute, ast.Subscript, ast.Lambda, ast.ListComp, ast.DictComp)):
            raise TopologyExpressionError(f"unsupported expression element: {node.__class__.__name__}")
        if isinstance(node, ast.BinOp) and type(node.op) not in _OPS:
            raise TopologyExpressionError(f"unsupported arithmetic operator: {node.op.__class__.__name__}")
    return {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}


def solve_parameter_for_metric(
    expression: str,
    *,
    target_metric_value: float,
    parameter_name: str,
    parameters: dict[str, Any],
    safe_bounds: tuple[float, float],
    iterations: int = 80,
) -> float:
    """Solve a monotonic manifest mapping by deterministic bounded bisection."""

    low, high = map(float, safe_bounds)
    if low >= high:
        raise TopologyExpressionError("safe bounds must be increasing")

    def residual(value: float) -> float:
        candidate = dict(parameters)
        candidate[parameter_name] = value
        return evaluate_numeric_expression(expression, candidate) - float(target_metric_value)

    low_value = residual(low)
    high_value = residual(high)
    if low_value == 0:
        return low
    if high_value == 0:
        return high
    if low_value * high_value > 0:
        raise TopologyExpressionError("target metric is outside the parameter safe bounds")
    for _ in range(iterations):
        midpoint = (low + high) / 2.0
        middle_value = residual(midpoint)
        if middle_value == 0:
            return midpoint
        if low_value * middle_value <= 0:
            high = midpoint
        else:
            low = midpoint
            low_value = middle_value
    return (low + high) / 2.0
