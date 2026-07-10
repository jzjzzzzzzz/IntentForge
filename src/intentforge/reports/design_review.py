"""Design review report generation for supported IntentForge models."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from intentforge.features import feature_flags_for_parameter_table, is_feature_active
from intentforge.knowledge.schema import KnowledgeFinding
from intentforge.schemas import FeaturePlan, IntentSpec, ParameterTable, ValidationReport


LIMITATIONS_BY_FAMILY: dict[str, list[str]] = {
    "wall_mounted_bracket": [
        "Only mounting-plate style wall brackets are supported.",
        "Through-hole recognition is topology-informed but not full industrial feature recognition.",
        "Rounded-corner recognition is approximate and parameter-aware.",
        "Material, loading, tolerance, and manufacturing process are not solved automatically.",
    ],
    "l_bracket": [
        "Only plain L-brackets with 0 or 2 holes per leg are supported.",
        "No 4-hole L-bracket pattern or freeform hole placement is supported.",
        "No curved, adjustable, or sheet-metal unfold geometry is supported.",
        "Inside fillet intent is represented and validated, but robust inside-corner fillet geometry remains future work.",
        "Gusset recognition is topology-informed and approximate.",
    ],
}


def _model_dump(value: Any) -> Any:
    if hasattr(value, "model_dump") and callable(value.model_dump):
        return value.model_dump(mode="json")
    return value


def _validation_summary(validation_report: ValidationReport | dict[str, Any] | None) -> dict[str, Any]:
    if validation_report is None:
        return {
            "available": False,
            "valid": None,
            "total_checks": 0,
            "passed_checks": 0,
            "failed_checks": 0,
            "warning_count": 0,
            "warnings": [],
            "summary": "Validation report was not provided.",
        }
    report = _model_dump(validation_report)
    checks = report.get("checks", []) if isinstance(report, dict) else []
    failed = [check for check in checks if check.get("status") == "fail"]
    warnings = [
        check.get("message") or check.get("description")
        for check in checks
        if check.get("status") == "warning" or check.get("severity") == "warning"
    ]
    return {
        "available": True,
        "valid": bool(report.get("valid", not failed)),
        "total_checks": len(checks),
        "passed_checks": len([check for check in checks if check.get("status") in {"pass", "warning"}]),
        "failed_checks": len(failed),
        "warning_count": len(warnings),
        "warnings": warnings,
        "summary": report.get("summary", ""),
    }


def _topology_summary(topology_report: Any | None) -> dict[str, Any]:
    if topology_report is None:
        return {"available": False}
    report = _model_dump(topology_report)
    return {
        "available": True,
        "bounding_box_dimensions_mm": report.get("bounding_box_dimensions_mm"),
        "volume_mm3": report.get("volume_mm3"),
        "surface_area_mm2": report.get("surface_area_mm2"),
        "solid_count": report.get("solid_count"),
        "face_count": report.get("face_count"),
        "edge_count": report.get("edge_count"),
        "vertex_count": report.get("vertex_count"),
        "is_valid": report.get("is_valid"),
        "warning_count": len(report.get("warnings", []) or []),
    }


def _parameter_summary(parameter_table: ParameterTable) -> list[dict[str, Any]]:
    return [
        {
            "name": parameter.name,
            "value": parameter.value,
            "unit": parameter.unit,
            "source": parameter.source,
            "reason": parameter.reason,
        }
        for parameter in parameter_table.parameters
    ]


def _feature_summary(parameter_table: ParameterTable, feature_plan: FeaturePlan | None) -> dict[str, Any]:
    flags = feature_flags_for_parameter_table(parameter_table)
    active = sorted(name for name in flags if is_feature_active(flags, name))
    omitted = sorted(name for name in flags if not is_feature_active(flags, name))
    return {
        "active_features": active,
        "omitted_features": omitted,
        "feature_flags": flags,
        "feature_plan_steps": [
            {
                "id": step.id,
                "operation": step.operation,
                "reason": step.reason,
                "parameters": step.parameters,
            }
            for step in (feature_plan.steps if feature_plan is not None else [])
        ],
    }


def _warning_summary(
    validation: dict[str, Any],
    feature_recognition_report: dict[str, Any] | None,
    topology_report: Any | None,
) -> list[str]:
    warnings = list(validation.get("warnings", []))
    if feature_recognition_report:
        warnings.extend(feature_recognition_report.get("warnings", []) or [])
    topology = _model_dump(topology_report) if topology_report is not None else None
    if isinstance(topology, dict):
        warnings.extend(
            f"topology {warning.get('metric')}: {warning.get('message')}"
            for warning in topology.get("warnings", []) or []
            if isinstance(warning, dict)
        )
    return [warning for warning in warnings if warning]


def generate_design_review_report(
    *,
    intent_spec: IntentSpec | dict[str, Any] | None,
    parameter_table: ParameterTable,
    feature_plan: FeaturePlan | None = None,
    validation_report: ValidationReport | dict[str, Any] | None = None,
    topology_report: Any | None = None,
    volume_delta_report: dict[str, Any] | None = None,
    feature_recognition_report: dict[str, Any] | None = None,
    knowledge_findings: list[KnowledgeFinding] | list[dict[str, Any]] | None = None,
    design_rationale: str | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Build a user-facing design review report from IntentForge artifacts."""

    intent = _model_dump(intent_spec) if intent_spec is not None else None
    validation = _validation_summary(validation_report)
    topology = _topology_summary(topology_report)
    features = _feature_summary(parameter_table, feature_plan)
    warnings = _warning_summary(validation, feature_recognition_report, topology_report)
    dumped_knowledge_findings = [_model_dump(finding) for finding in (knowledge_findings or [])]

    report = {
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "object_type": parameter_table.family,
        "requested": {
            "prompt": intent.get("user_prompt") if isinstance(intent, dict) else None,
            "objective": intent.get("objective") if isinstance(intent, dict) else None,
            "requirements": intent.get("requirements", []) if isinstance(intent, dict) else [],
            "assumptions": intent.get("assumptions", parameter_table.assumptions) if isinstance(intent, dict) else parameter_table.assumptions,
            "unknowns": intent.get("unknowns", parameter_table.unknowns) if isinstance(intent, dict) else parameter_table.unknowns,
        },
        "model_family": parameter_table.family,
        "parameters": _parameter_summary(parameter_table),
        "features": features,
        "validation": validation,
        "topology": topology,
        "volume_delta": volume_delta_report or {"available": False},
        "feature_recognition": feature_recognition_report or {"available": False},
        "knowledge_findings": dumped_knowledge_findings,
        "design_rationale": design_rationale,
        "warnings": warnings,
        "artifacts": artifacts or [],
        "limitations": LIMITATIONS_BY_FAMILY.get(parameter_table.family, []),
    }
    report["trusted_for_basic_review"] = (
        validation["valid"] is not False
        and (feature_recognition_report or {}).get("passed", True) is not False
    )
    return report


def design_review_summary_markdown(report: dict[str, Any]) -> str:
    """Render a compact Markdown design review summary."""

    validation = report["validation"]
    topology = report["topology"]
    recognition = report["feature_recognition"]
    lines = [
        f"# IntentForge Design Review: {report['object_type']}",
        "",
        "## Request",
        f"- Prompt: {report['requested'].get('prompt') or 'not recorded'}",
        f"- Objective: {report['requested'].get('objective') or 'not recorded'}",
        "",
        "## Parameters",
    ]
    for parameter in report["parameters"]:
        unit = f" {parameter['unit']}" if parameter.get("unit") else ""
        lines.append(f"- {parameter['name']}: {parameter['value']}{unit} ({parameter['source']})")

    lines.extend(
        [
            "",
            "## Features",
            f"- Active: {', '.join(report['features']['active_features']) if report['features']['active_features'] else 'none'}",
            f"- Omitted: {', '.join(report['features']['omitted_features']) if report['features']['omitted_features'] else 'none'}",
            "",
            "## Validation",
            f"- Valid: {str(validation['valid']).lower()}",
            f"- Checks: {validation['passed_checks']}/{validation['total_checks']} passed, {validation['failed_checks']} failed",
            f"- Warnings: {validation['warning_count']}",
            "",
            "## Topology",
            f"- Bounding box: {topology.get('bounding_box_dimensions_mm')}",
            f"- Volume: {topology.get('volume_mm3')} mm^3",
            f"- Solid count: {topology.get('solid_count')}",
            f"- Shape valid: {topology.get('is_valid')}",
            "",
            "## Feature Recognition",
            f"- Passed: {str(recognition.get('passed')).lower() if isinstance(recognition, dict) and 'passed' in recognition else 'not available'}",
        ]
    )
    for name, feature in (recognition.get("recognized_features", {}) if isinstance(recognition, dict) else {}).items():
        lines.append(f"- {name}: confidence={feature.get('confidence')}, passed={feature.get('passed')}")

    knowledge_findings = report.get("knowledge_findings", [])
    lines.extend(["", "## Engineering Knowledge"])
    if knowledge_findings:
        failed_findings = [finding for finding in knowledge_findings if not finding.get("passed")]
        lines.append(f"- Findings: {len(knowledge_findings)} total, {len(failed_findings)} advisory findings")
        for finding in failed_findings:
            lines.append(
                f"- {finding.get('severity', 'warning').upper()}: {finding.get('rule_name')} - {finding.get('recommendation')}"
            )
    else:
        lines.append("- Not requested for this report.")

    lines.extend(["", "## Remaining Warnings"])
    if report["warnings"]:
        lines.extend(f"- {warning}" for warning in report["warnings"])
    else:
        lines.append("- none")

    lines.extend(["", "## Artifacts"])
    if report["artifacts"]:
        for artifact in report["artifacts"]:
            lines.append(f"- {artifact.get('kind', 'artifact')}: {artifact.get('path')}")
    else:
        lines.append("- none")

    lines.extend(["", "## Limitations"])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def write_design_review_report(report: dict[str, Any], path: str | Path) -> Path:
    """Write a design review JSON report."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def write_design_review_summary(report: dict[str, Any], path: str | Path) -> Path:
    """Write a Markdown design review summary."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(design_review_summary_markdown(report), encoding="utf-8")
    return output_path
