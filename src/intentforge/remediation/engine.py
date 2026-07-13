"""Deterministic auto-remediation engine for IntentForge Phase 30.

This module glues the algebraic inversion primitive
(:mod:`intentforge.remediation.algebra`) to the rejected audit-package
workflow. Given a package directory whose ``review_decision.json`` reports
``rejected_by_policy`` or ``accepted_with_conditions``, the engine:

1. Reads the package's parameter table (from an optional ``parameters.json``
   payload, the assurance case's structured intent, or a caller-supplied
   parameter dictionary).
2. Recomputes the engineering metrics via
   :func:`intentforge.knowledge.evaluator.build_design_metrics`.
3. Selects the failing knowledge findings whose expressions are within the
   algebraic grammar.
4. Asks the algebra engine to compute the nearest compliant boundary
   state, yielding a :class:`RemediationDelta`.
5. Writes a deterministic ``Remediation_Intent.json`` summarizing the
   proposed parameter changes, the boundary inequality that motivated each
   change, and the remediation status.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from intentforge.knowledge.evaluator import build_design_metrics
from intentforge.knowledge.rules import RuleRegistry
from intentforge.remediation.algebra import (
    REMEDIATION_ENGINE_VERSION,
    RemediationDelta,
    extract_metric_to_parameter_map,
    synthesize_remediation,
)


REMEDIATION_INTENT_FILE = "Remediation_Intent.json"
REMEDIATION_INTENT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class RemediationEngineResult:
    """Result of running the auto-remediation engine on a rejected package."""

    passed: bool
    status: str  # "remediation_synthesized", "remediation_impossible", or "skipped"
    delta: RemediationDelta | None
    remediation_path: Path | None
    rationale: str
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "passed": self.passed,
            "status": self.status,
            "rationale": self.rationale,
            "errors": list(self.errors),
        }
        if self.delta is not None:
            payload["delta"] = self.delta.to_dict()
        if self.remediation_path is not None:
            payload["remediation_path"] = str(self.remediation_path)
        return payload


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_parameters(
    raw: Any,
) -> dict[str, Any]:
    """Adapt a raw parameter-table dictionary into a flat name->value map."""

    if not isinstance(raw, dict):
        return {}
    if "parameters" in raw and isinstance(raw["parameters"], list):
        params = raw["parameters"]
        flat: dict[str, Any] = {}
        for item in params:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str):
                flat[name] = item.get("value")
        return flat
    if all(isinstance(v, (int, float, bool)) for v in raw.values()):
        return dict(raw)
    return dict(raw)


def _load_parameter_table_from_package(
    package_path: Path,
) -> dict[str, Any]:
    candidates = [
        package_path / "parameters.json",
        package_path / "parameter_table.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                raw = _read_json(path)
                return _normalize_parameters(raw)
            except (OSError, json.JSONDecodeError):
                continue
    case_path = package_path / "assurance_case.json"
    if case_path.is_file():
        try:
            case = _read_json(case_path)
            intent = case.get("structured_intent") or {}
            if isinstance(intent, dict):
                params = intent.get("parameters")
                if isinstance(params, dict):
                    return _normalize_parameters(params)
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def _load_metrics_and_family(
    package_path: Path,
    *,
    parameters_override: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], dict[str, float]]:
    manifest = _read_json(package_path / "manifest.json") if (package_path / "manifest.json").is_file() else {}
    family = manifest.get("cad_family") or "wall_mounted_bracket"
    from intentforge.topology.registry import get_topology_registry

    get_topology_registry().get(str(family))
    parameters = parameters_override or _load_parameter_table_from_package(package_path)
    metrics = build_metrics(parameters, family=family)
    return family, parameters, metrics


def build_metrics(parameters: dict[str, Any], *, family: str) -> dict[str, float]:
    """Compute the deterministic engineering metrics for the parameter table."""

    metrics: dict[str, Any] = {"family": family}
    if family == "wall_mounted_bracket":
        width = _numeric(parameters.get("back_plate_width_mm"))
        height = _numeric(parameters.get("back_plate_height_mm"))
        thickness = _numeric(parameters.get("back_plate_thickness_mm"))
        hole_diameter = _numeric(parameters.get("mounting_hole_diameter_mm"))
        spacing = _numeric(parameters.get("mounting_hole_spacing_x_mm"))
        spacing_y = _numeric(parameters.get("mounting_hole_spacing_y_mm"))
        corner_radius = _numeric(parameters.get("corner_radius_mm"))
        cutout_width = _numeric(parameters.get("center_cutout_width_mm"))
        cutout_height = _numeric(parameters.get("center_cutout_height_mm"))
        holes_active = _bool(parameters.get("feature_flags", {}), "mounting_holes") if isinstance(parameters.get("feature_flags"), dict) else True
        center_cutout_active = _bool(parameters.get("feature_flags", {}), "center_cutout") if isinstance(parameters.get("feature_flags"), dict) else (cutout_width > 0 and cutout_height > 0)
        rounded_corners_active = _bool(parameters.get("feature_flags", {}), "rounded_corners") if isinstance(parameters.get("feature_flags"), dict) else (corner_radius > 0)
        if holes_active:
            x_edge = width / 2 - spacing / 2 - hole_diameter / 2
            y_edge = height / 2 - spacing_y / 2 - hole_diameter / 2
            hole_edge_distance = min(x_edge, y_edge)
            hole_spacing = min(spacing, spacing_y) if spacing_y else spacing
        else:
            hole_edge_distance = 0.0
            hole_spacing = 0.0
        cutout_area_ratio = (cutout_width * cutout_height / (width * height)) if width > 0 and height > 0 and center_cutout_active else 0.0
        cutout_web = min((width - cutout_width) / 2, (height - cutout_height) / 2) if center_cutout_active else min(width, height)
        tool_clearance = _min_positive([hole_diameter if holes_active else None, min(cutout_width, cutout_height) if center_cutout_active else None, width, height])
        active_feature_count = sum(1 for value in parameters.get("feature_flags", {}).values() if value) if isinstance(parameters.get("feature_flags"), dict) else 0
        metrics.update({
            "object_type": family,
            "width": width,
            "height": height,
            "thickness": thickness,
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
            "active_optional_feature_count": active_feature_count,
        })
    elif family == "l_bracket":
        base_length = _numeric(parameters.get("base_leg_length_mm"))
        vertical_length = _numeric(parameters.get("vertical_leg_length_mm"))
        bracket_width = _numeric(parameters.get("bracket_width_mm"))
        thickness = _numeric(parameters.get("thickness_mm"))
        hole_diameter = _numeric(parameters.get("hole_diameter_mm"))
        base_spacing = _numeric(parameters.get("base_hole_spacing_mm"))
        vertical_spacing = _numeric(parameters.get("vertical_hole_spacing_mm"))
        base_count = _numeric(parameters.get("base_hole_count"))
        vertical_count = _numeric(parameters.get("vertical_hole_count"))
        corner_radius = _numeric(parameters.get("outside_edge_fillet_radius_mm"))
        flags = parameters.get("feature_flags") if isinstance(parameters.get("feature_flags"), dict) else {}
        base_active = (bool(flags.get("base_mounting_holes")) if flags else base_count > 0)
        vertical_active = (bool(flags.get("vertical_mounting_holes")) if flags else vertical_count > 0)
        holes_active = base_active or vertical_active
        edge_distances = []
        spacings = []
        if base_active:
            edge_distances.append(min(base_length / 2 - base_spacing / 2 - hole_diameter / 2, bracket_width / 2 - hole_diameter / 2))
            spacings.append(base_spacing)
        if vertical_active:
            edge_distances.append(min(vertical_length / 2 - vertical_spacing / 2 - hole_diameter / 2, bracket_width / 2 - hole_diameter / 2))
            spacings.append(vertical_spacing)
        gusset_enabled = bool(flags.get("triangular_gusset")) if flags else bool(parameters.get("gusset_enabled", False))
        rounded_corners_active = bool(flags.get("outside_edge_fillets")) if flags else corner_radius > 0
        active_feature_count = sum(1 for v in flags.values() if v) if flags else 0
        metrics.update({
            "object_type": family,
            "base_leg_length": base_length,
            "vertical_leg_length": vertical_length,
            "bracket_width": bracket_width,
            "thickness": thickness,
            "hole_diameter": hole_diameter,
            "hole_spacing": min(spacings) if spacings else 0.0,
            "hole_edge_distance": min(edge_distances) if edge_distances else 0.0,
            "fastener_edge_clearance": min(edge_distances) if edge_distances else 0.0,
            "mounting_holes_active": holes_active,
            "base_mounting_holes_active": base_active,
            "vertical_mounting_holes_active": vertical_active,
            "gusset_enabled": gusset_enabled,
            "vertical_leg_height_to_thickness": vertical_length / thickness if thickness > 0 else 0.0,
            "minimum_section_thickness": min(bracket_width, base_length, vertical_length),
            "tool_clearance": _min_positive([hole_diameter if holes_active else None, bracket_width, thickness]),
            "corner_radius": corner_radius,
            "rounded_corners_active": rounded_corners_active,
            "center_cutout_active": False,
            "cutout_area_ratio": 0.0,
            "active_optional_feature_count": active_feature_count,
        })
    else:
        from intentforge.topology.expressions import evaluate_numeric_expression
        from intentforge.topology.registry import get_topology_registry

        manifest = get_topology_registry().get(family)
        for mapping in manifest.capability_evidence_binding.rule_variable_mapping:
            metrics[mapping.metric] = evaluate_numeric_expression(mapping.expression, parameters)
        outer = _numeric(parameters.get("flange_outer_diameter", metrics.get("pitch_circle_diameter", parameters.get("nominal_diameter"))))
        bore = _numeric(parameters.get("bore_diameter"))
        hole_diameter = _numeric(parameters.get("bolt_hole_diameter", parameters.get("bore_diameter")))
        thickness = _numeric(parameters.get("flange_thickness", parameters.get("face_width", parameters.get("thread_pitch"))))
        hole_count = _numeric(parameters.get("hole_count", 1.0 if family == "spur_gear" else 0.0))
        metrics.update({
            "object_type": family,
            "width": outer,
            "height": outer,
            "bracket_width": outer,
            "thickness": thickness,
            "hole_diameter": hole_diameter,
            "hole_count": hole_count,
            "mounting_holes_active": hole_count > 0,
            "fastener_edge_clearance": metrics.get("hole_edge_distance", 0.0),
            "tool_clearance": metrics.get("tool_clearance", _min_positive([hole_diameter, thickness])),
            "minimum_section_thickness": metrics.get("minimum_section_thickness", max(0.0, (outer - bore) / 2.0)),
            "corner_radius": 0.0,
            "rounded_corners_active": False,
            "center_cutout_active": False,
            "cutout_area_ratio": 0.0,
            "gusset_enabled": False,
            "vertical_leg_height_to_thickness": 0.0,
            "active_optional_feature_count": len(manifest.supported_features),
        })
    return metrics


def _numeric(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bool(flags: dict[str, Any], key: str) -> bool:
    value = flags.get(key)
    return bool(value)


def _min_positive(values: list[float | None]) -> float:
    positives = [v for v in values if v is not None and v > 0]
    return min(positives) if positives else 0.0


def _load_rule_registry(family: str | None = None) -> dict[str, dict[str, Any]]:
    registry = RuleRegistry.load()
    payload: dict[str, dict[str, Any]] = {}
    selected = registry.for_family(family) if family else registry.rules
    for rule in selected:
        if rule.status != "active":
            continue
        payload[rule.id] = {
            "id": rule.id,
            "name": rule.name,
            "condition": rule.condition,
            "applies_to": sorted(set(rule.applies_to).union({family} if family else set())),
            "severity": rule.severity,
            "recommendation": rule.recommendation,
            "reasoning": rule.reasoning,
        }
    return payload


def _extract_failed_findings(
    *,
    family: str,
    parameters: dict[str, Any],
    metrics: dict[str, float],
    rule_registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compute the active knowledge findings directly from the rule registry.

    This complements the package's review_decision.json by re-running the
    metric evaluation against the persisted parameter table.
    """

    from intentforge.knowledge.evaluator import evaluate_expression

    failed: list[dict[str, Any]] = []
    for rule in rule_registry.values():
        condition = rule.get("condition", {})
        expression = condition.get("expression") if isinstance(condition, dict) else None
        if not isinstance(expression, str):
            continue
        when = condition.get("when") if isinstance(condition, dict) else None
        if isinstance(when, dict):
            skip = False
            for key, expected in when.items():
                if metrics.get(key) != expected:
                    skip = True
                    break
            if skip:
                continue
        try:
            passed = bool(evaluate_expression(expression, metrics))
        except Exception:  # noqa: BLE001
            continue
        if passed:
            continue
        failed.append({
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "severity": rule.get("severity"),
            "metrics": {key: metrics.get(key) for key in condition.get("required_metrics", [])},
        })
    return failed


def synthesize_remediation_intent(
    package_path: str | Path,
    *,
    parameters_override: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
) -> RemediationEngineResult:
    """Analyze a rejected audit package and emit a Remediation_Intent.json."""

    package_dir = Path(package_path)
    if not package_dir.is_dir():
        return RemediationEngineResult(
            passed=False, status="remediation_impossible", delta=None, remediation_path=None,
            rationale="package directory does not exist",
            errors=("package directory does not exist",),
        )
    try:
        family, parameters, metrics = _load_metrics_and_family(
            package_dir, parameters_override=parameters_override,
        )
    except (OSError, json.JSONDecodeError) as exc:
        return RemediationEngineResult(
            passed=False, status="remediation_impossible", delta=None, remediation_path=None,
            rationale=f"could not load package metadata: {exc}",
            errors=(str(exc),),
        )
    if not parameters:
        return RemediationEngineResult(
            passed=False, status="remediation_impossible", delta=None, remediation_path=None,
            rationale="package does not expose a parameter table; supply --parameters to remediate",
            errors=("parameter table unavailable",),
        )
    rule_registry = _load_rule_registry(family=family)
    failed_findings = _extract_failed_findings(
        family=family, parameters=parameters, metrics=metrics, rule_registry=rule_registry,
    )
    if not failed_findings:
        return RemediationEngineResult(
            passed=True, status="skipped", delta=None, remediation_path=None,
            rationale="package has no failed knowledge findings; nothing to remediate",
        )
    delta = synthesize_remediation(
        family=family,
        parameters=parameters,
        metrics=metrics,
        failed_findings=failed_findings,
        rule_registry=rule_registry,
    )
    target_dir = Path(output_dir) if output_dir else package_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    intent_payload = {
        "schema_version": REMEDIATION_INTENT_SCHEMA_VERSION,
        "remediation_id": delta.remediation_id,
        "remediation_status": delta.remediation_status,
        "target_family": delta.target_family,
        "source_metrics": delta.source_metrics,
        "proposed_parameters": delta.proposed_parameters,
        "parameter_changes": [action.to_dict() for action in delta.parameter_changes],
        "plans": [plan.to_dict() for plan in delta.plans],
        "rationale": delta.rationale,
        "remediation_engine_version": REMEDIATION_ENGINE_VERSION,
    }
    intent_bytes = _canonical_json_bytes(intent_payload)
    intent_path = target_dir / REMEDIATION_INTENT_FILE
    intent_path.write_bytes(intent_bytes)
    return RemediationEngineResult(
        passed=(delta.remediation_status == "remediation_synthesized"),
        status=delta.remediation_status,
        delta=delta,
        remediation_path=intent_path,
        rationale=delta.rationale,
    )


def apply_remediation_to_parameters(
    parameters: dict[str, Any],
    remediation_intent: dict[str, Any],
) -> dict[str, Any]:
    """Apply a Remediation_Intent to a parameter table, returning a new dict."""

    applied = dict(parameters)
    for change in remediation_intent.get("parameter_changes", []):
        name = change.get("parameter")
        value = change.get("proposed_value")
        if isinstance(name, str) and isinstance(value, (int, float)):
            applied[name] = float(value)
    return applied


__all__ = [
    "REMEDIATION_INTENT_FILE",
    "REMEDIATION_INTENT_SCHEMA_VERSION",
    "RemediationEngineResult",
    "RemediationEngineVersion",
    "apply_remediation_to_parameters",
    "build_metrics",
    "synthesize_remediation_intent",
]
