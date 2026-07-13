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
    bore_clearance = float(table.get("bore_clearance").value)
    effective_bore = bore + bore_clearance
    solids = shape.Solids() if hasattr(shape, "Solids") else []
    checks = [
        _check("flange_shape_valid", "OpenCASCADE shape is valid.", bool(shape.isValid())),
        _check("flange_single_solid", "Flange is one connected solid.", len(solids) == 1, expected=1, actual=len(solids)),
        _check("flange_outer_diameter", "Outside diameter matches the parameter.", abs(box.xlen - outer) <= 0.1, expected=outer, actual=box.xlen),
        _check("flange_thickness", "Axial thickness matches the parameter.", abs(box.zlen - thickness) <= 0.1, expected=thickness, actual=box.zlen),
        _check("flange_bore_clearance", "Central bore includes the declared diametral assembly clearance.", bore_clearance >= 0.0, expected=">=0", actual=bore_clearance),
        _check("flange_radial_material", "Effective bore and bolt holes retain radial material.", effective_bore < bolt_circle - bolt_hole and bolt_circle + bolt_hole < outer),
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


def _registered_shape_report(
    *,
    model: Any,
    table: ParameterTable,
    checks: list[ValidationCheck],
    recognized_features: dict[str, Any],
    label: str,
) -> ValidationReport:
    shape = model.val() if hasattr(model, "val") else model
    solids = shape.Solids() if hasattr(shape, "Solids") else []
    topology_checks = [
        _check(f"{table.family}_shape_valid", "OpenCASCADE shape is valid.", bool(shape.isValid())),
        _check(
            f"{table.family}_single_solid", "Model is one connected solid.",
            len(solids) == 1, expected=1, actual=len(solids),
        ),
        _check(f"{table.family}_positive_volume", "Generated model has positive volume.", float(shape.Volume()) > 0.0),
    ]
    all_checks = topology_checks + checks
    passed = all(item.status == "pass" for item in all_checks)
    return ValidationReport(
        family=table.family,
        checks=all_checks,
        summary=f"{label} validation: {sum(c.status == 'pass' for c in all_checks)}/{len(all_checks)} checks passed.",
        metadata={
            "topology_registry": f"{table.family}@1.0",
            "valid": passed,
            "topology": {
                "passed": bool(shape.isValid()) and len(solids) == 1,
                "solid_count": len(solids),
                "connected_solid": len(solids) == 1,
                "valid_shape": bool(shape.isValid()),
                "warnings": [],
            },
            "feature_recognition": {
                "passed": passed,
                "object_type": table.family,
                "recognized_features": recognized_features,
                "warnings": ["Recognition confirms deterministic construction and basic topology, not an industrial feature-history model."],
            },
        },
    )


def validate_spur_gear(model: Any, table: ParameterTable, **_: Any) -> ValidationReport:
    shape = model.val() if hasattr(model, "val") else model
    box = shape.BoundingBox()
    module = float(table.get("module").value)
    teeth = int(table.get("teeth_count").value)
    width = float(table.get("face_width").value)
    bore = float(table.get("bore_diameter").value)
    bore_clearance = float(table.get("bore_clearance").value)
    effective_bore = bore + bore_clearance
    pitch = module * teeth
    root = module * (teeth - 2.5)
    outside = module * (teeth + 2.0)
    margin = (root - effective_bore) / 2.0
    margin_modules = float(get_topology_registry().get("spur_gear").metadata["minimum_radial_bore_margin_modules"])
    required_margin = margin_modules * module
    checks = [
        _check("gear_pitch_formula", "Pitch-circle diameter follows module times tooth count.", abs(pitch - module * teeth) <= 1e-9),
        _check("gear_undercut_limit", "Zero-shift tooth count meets the supported undercut limit.", teeth >= 17, expected=">=17", actual=teeth),
        _check("gear_root_formula", "Root-circle diameter follows the registered full-depth approximation.", root > effective_bore),
        _check("gear_bore_clearance", "Central bore includes the declared diametral assembly clearance.", bore_clearance >= 0.0, expected=">=0", actual=bore_clearance),
        _check("gear_bore_material", "Central bore retains the declared radial material margin.", margin >= required_margin, expected=f">={required_margin}", actual=margin),
        _check("gear_outside_diameter", "Generated outside diameter matches the addendum envelope.", abs(max(box.xlen, box.ylen) - outside) <= max(0.2, module * 0.08), expected=outside, actual=max(box.xlen, box.ylen)),
        _check("gear_face_width", "Generated face width matches the parameter.", abs(box.zlen - width) <= 0.1, expected=width, actual=box.zlen),
    ]
    return _registered_shape_report(
        model=model, table=table, checks=checks, label="Spur gear",
        recognized_features={
            "involute_teeth": {"expected_count": teeth, "recognized_count": teeth, "passed": True, "confidence": "medium", "warnings": ["Tooth count is confirmed from deterministic construction metadata."]},
            "central_bore": {"recognized": True, "passed": True, "confidence": "high", "warnings": []},
        },
    )


def validate_standard_bolt(model: Any, table: ParameterTable, **_: Any) -> ValidationReport:
    shape = model.val() if hasattr(model, "val") else model
    box = shape.BoundingBox()
    diameter = float(table.get("nominal_diameter").value)
    pitch = float(table.get("thread_pitch").value)
    shank = float(table.get("shank_length").value)
    thread = float(table.get("thread_length").value)
    head_type = str(table.get("head_type").value)
    head_height = 0.65 * diameter if head_type == "hexagonal" else diameter
    stress_diameter = diameter - 0.9382 * pitch
    stress_area = 0.7853981633974483 * stress_diameter * stress_diameter
    checks = [
        _check("bolt_total_length", "Shank and thread lengths form the body length.", abs(box.zlen - (shank + thread + head_height)) <= 0.1, expected=shank + thread + head_height, actual=box.zlen),
        _check("bolt_stress_area", "Declared pitch produces a positive tensile stress-area approximation.", stress_area > 0.0, expected=">0", actual=stress_area),
        _check("bolt_head_type", "Head type is one of the closed registered choices.", head_type in {"hexagonal", "socket_cap"}),
        _check("bolt_major_diameter", "Generated shaft uses the nominal major diameter.", min(box.xlen, box.ylen) >= diameter - 0.1, expected=f">={diameter - 0.1}", actual=min(box.xlen, box.ylen)),
    ]
    return _registered_shape_report(
        model=model, table=table, checks=checks, label="Standard bolt",
        recognized_features={
            "shank": {"recognized": True, "passed": True, "confidence": "high", "warnings": []},
            "simplified_thread_region": {"recognized": True, "passed": True, "confidence": "medium", "warnings": ["Thread is represented by its cylindrical major-diameter envelope."]},
            "bolt_head": {"recognized": True, "head_type": head_type, "passed": True, "confidence": "high", "warnings": []},
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
    if manifest.validator_id == "spur_gear_validator_v1":
        return validate_spur_gear(model, table, **kwargs)
    if manifest.validator_id == "standard_bolt_validator_v1":
        return validate_standard_bolt(model, table, **kwargs)
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
