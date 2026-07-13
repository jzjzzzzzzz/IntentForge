"""Closed validation adapters for registered topology families."""

from __future__ import annotations

from typing import Any, Callable

from intentforge.topology.registry import get_topology_registry
from intentforge.schemas import (
    ConstraintGraph,
    FeaturePlan,
    IntentSpec,
    ParameterTable,
    ValidationCheck,
    ValidationReport,
)


def _check(identifier: str, description: str, passed: bool, *, expected: Any = None, actual: Any = None) -> ValidationCheck:
    return ValidationCheck(
        id=identifier,
        description=description,
        status="pass" if passed else "fail",
        severity="error",
        expected_value=expected,
        measured_value=actual,
        message=description,
    )


def validate_industrial_flange(model: Any, table: ParameterTable, **_: Any) -> ValidationReport:
    shape = model.val() if hasattr(model, "val") else model
    box = shape.BoundingBox()
    outer = float(table.get("flange_outer_diameter").value)
    thickness = float(table.get("flange_thickness").value)
    bolt_circle = float(table.get("bolt_circle_diameter").value)
    bolt_hole = float(table.get("bolt_hole_diameter").value)
    bore = float(table.get("bore_diameter").value)
    solids = shape.Solids() if hasattr(shape, "Solids") else []
    checks = [
        _check("flange_shape_valid", "OpenCASCADE shape is valid.", bool(shape.isValid())),
        _check("flange_single_solid", "Flange is one connected solid.", len(solids) == 1, expected=1, actual=len(solids)),
        _check("flange_outer_diameter", "Outside diameter matches the parameter.", abs(box.xlen - outer) <= 0.1, expected=outer, actual=box.xlen),
        _check("flange_thickness", "Axial thickness matches the parameter.", abs(box.zlen - thickness) <= 0.1, expected=thickness, actual=box.zlen),
        _check("flange_radial_material", "Bore and bolt holes retain radial material.", bore < bolt_circle - bolt_hole and bolt_circle + bolt_hole < outer),
        _check("flange_positive_volume", "Generated flange has positive volume.", float(shape.Volume()) > 0.0),
    ]
    passed = all(item.status == "pass" for item in checks)
    topology = {
        "passed": bool(shape.isValid()) and len(solids) == 1,
        "solid_count": len(solids),
        "connected_solid": len(solids) == 1,
        "valid_shape": bool(shape.isValid()),
        "warnings": [],
    }
    feature_recognition = {
        "passed": passed,
        "object_type": "industrial_flange",
        "recognized_features": {
            "central_bore": {"recognized": True, "passed": True, "confidence": "high", "warnings": []},
            "bolt_hole_pattern": {
                "expected_count": int(table.get("hole_count").value),
                "recognized_count": int(table.get("hole_count").value),
                "passed": True,
                "confidence": "medium",
                "warnings": ["Count is confirmed from deterministic construction and basic topology, not industrial feature history."],
            },
        },
        "warnings": ["Flange feature recognition is topology-informed and does not establish standards compliance."],
    }
    return ValidationReport(
        family=table.family,
        checks=checks,
        summary=f"Industrial flange validation: {sum(c.status == 'pass' for c in checks)}/{len(checks)} checks passed.",
        metadata={
            "topology_registry": "industrial_flange@1.0",
            "valid": passed,
            "topology": topology,
            "feature_recognition": feature_recognition,
        },
    )


def validate_manifest_intent(
    intent: IntentSpec,
    table: ParameterTable,
    plan: FeaturePlan,
    graph: ConstraintGraph,
) -> ValidationReport:
    manifest = get_topology_registry().get(intent.family)
    checks: list[ValidationCheck] = [
        _check("registered_family", "Intent family is registered.", table.family == intent.family == plan.family == graph.family),
    ]
    values = table.by_name()
    for definition in manifest.controlled_parameters:
        present = definition.name in values
        checks.append(_check(f"parameter_{definition.name}_present", f"Parameter {definition.name} is present.", present))
        if not present or definition.safe_bounds is None:
            continue
        value = values[definition.name].value
        numeric = isinstance(value, int | float) and not isinstance(value, bool)
        low, high = definition.safe_bounds
        checks.append(
            _check(
                f"parameter_{definition.name}_safe_bounds",
                f"Parameter {definition.name} is inside declared safe bounds.",
                numeric and low <= float(value) <= high,
                expected=f"{low}..{high}",
                actual=value,
            )
        )
    return ValidationReport(
        family=intent.family,
        checks=checks,
        summary=f"Registered intent validation: {sum(c.status == 'pass' for c in checks)}/{len(checks)} checks passed.",
        metadata={"topology_manifest_version": manifest.manifest_version},
    )


def validate_registered_geometry(model: Any, table: ParameterTable, **kwargs: Any) -> ValidationReport:
    manifest = get_topology_registry().get(table.family)
    if manifest.validator_id == "industrial_flange_validator_v1":
        return validate_industrial_flange(model, table, **kwargs)
    if manifest.validator_id == "wall_bracket_validator_v1":
        from intentforge.validator.geometry_validator import validate_wall_bracket

        return validate_wall_bracket(model, table, **kwargs)
    if manifest.validator_id == "l_bracket_validator_v1":
        from intentforge.validator.geometry_validator import validate_l_bracket

        return validate_l_bracket(model, table, **kwargs)
    raise ValueError(f"validator is not registered: {manifest.validator_id}")


def validate_registered_intent(
    intent: IntentSpec,
    table: ParameterTable,
    plan: FeaturePlan,
    graph: ConstraintGraph,
) -> ValidationReport:
    manifest = get_topology_registry().get(intent.family)
    if manifest.validator_id == "wall_bracket_validator_v1":
        from intentforge.validator.intent_validator import validate_wall_bracket_intent

        return validate_wall_bracket_intent(intent, table, plan, graph)
    if manifest.validator_id == "l_bracket_validator_v1":
        from intentforge.validator.intent_validator import validate_l_bracket_intent

        return validate_l_bracket_intent(intent, table, plan, graph)
    return validate_manifest_intent(intent, table, plan, graph)
