"""Orchestrator for deterministic engineering reasoning reports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from intentforge.knowledge.report import KnowledgeReport
from intentforge.knowledge.rules import RuleRegistry
from intentforge.knowledge.schema import KnowledgeFinding
from intentforge.knowledge.reasoning.conflicts import detect_reasoning_conflicts
from intentforge.knowledge.reasoning.interactions import detect_rule_interactions
from intentforge.knowledge.reasoning.recommendations import generate_recommendations
from intentforge.knowledge.reasoning.schema import (
    EngineeringReasoningReport,
    REASONING_ENGINE_VERSION,
    ReasoningStep,
    make_reasoning_report_id,
)
from intentforge.knowledge.reasoning.tradeoffs import generate_tradeoffs


SUPPORTED_REASONING_FAMILIES = (
    "wall_mounted_bracket", "l_bracket", "industrial_flange", "spur_gear", "standard_bolt",
)

DEFAULT_REASONING_LIMITATIONS = [
    "This report uses deterministic engineering heuristics.",
    "It does not replace load-specific engineering analysis, testing, FEA, or professional approval.",
    "It does not certify safety or structural performance.",
    "Recommendations are advisory and do not automatically modify CAD geometry.",
]


class EngineeringReasoningError(ValueError):
    """Raised when reasoning inputs are malformed or unsupported."""


def _knowledge_report_data(knowledge_report: KnowledgeReport | dict[str, Any]) -> dict[str, Any]:
    if isinstance(knowledge_report, KnowledgeReport):
        return knowledge_report.model_dump(mode="json")
    if isinstance(knowledge_report, dict):
        return knowledge_report
    raise EngineeringReasoningError("knowledge_report must be a KnowledgeReport or mapping")


def _findings_from_report(knowledge_report: KnowledgeReport | dict[str, Any]) -> list[KnowledgeFinding]:
    data = _knowledge_report_data(knowledge_report)
    raw_findings = data.get("findings")
    if not isinstance(raw_findings, list):
        raise EngineeringReasoningError("knowledge_report.findings must be a list")
    return [finding if isinstance(finding, KnowledgeFinding) else KnowledgeFinding.model_validate(finding) for finding in raw_findings]


def _source_report_id(knowledge_report: KnowledgeReport | dict[str, Any]) -> str:
    data = _knowledge_report_data(knowledge_report)
    report_id = data.get("report_id")
    if not isinstance(report_id, str) or not report_id:
        raise EngineeringReasoningError("knowledge_report.report_id is required")
    return report_id


def _rule_versions_by_id(registry: RuleRegistry) -> dict[str, str]:
    return {rule.id: rule.rule_version for rule in registry.rules}


def _build_observations(
    findings: list[KnowledgeFinding],
    rule_versions: dict[str, str],
) -> list[ReasoningStep]:
    observations: list[ReasoningStep] = []
    for sequence, finding in enumerate(sorted(findings, key=lambda item: item.rule_id), start=1):
        statement = (
            f"{finding.rule_name} passed."
            if finding.passed
            else f"{finding.rule_name}: {finding.message}"
        )
        observations.append(
            ReasoningStep(
                step_id=f"observation_{sequence:03d}_{finding.rule_id}",
                step_type="observation",
                rule_ids=[finding.rule_id],
                statement=statement,
                evidence={
                    "passed": finding.passed,
                    "severity": finding.severity,
                    "category": finding.category,
                    "rule_version": finding.metadata.get("rule_version") or rule_versions.get(finding.rule_id),
                },
                confidence=finding.confidence,
                sequence=sequence,
            )
        )
    return observations


def _summary(
    *,
    observations: list[ReasoningStep],
    interactions_count: int,
    tradeoffs_count: int,
    conflicts_count: int,
    recommendations_count: int,
    high_priority_count: int,
) -> dict[str, Any]:
    failed_observations = [
        step
        for step in observations
        if step.evidence.get("passed") is False
    ]
    return {
        "findings_analyzed": len(observations),
        "advisory_findings": len(failed_observations),
        "interactions": interactions_count,
        "tradeoffs": tradeoffs_count,
        "conflicts": conflicts_count,
        "recommendations": recommendations_count,
        "high_priority_recommendations": high_priority_count,
    }


def build_engineering_reasoning_report(
    *,
    model_family: str,
    knowledge_report: KnowledgeReport | dict[str, Any],
    rule_registry: RuleRegistry | None = None,
    metrics: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
    feature_recognition_report: dict[str, Any] | None = None,
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> EngineeringReasoningReport:
    """Build a deterministic engineering reasoning report.

    This function is intentionally independent from CAD generation. It consumes
    evaluated knowledge findings and rule metadata only.
    """

    if model_family not in SUPPORTED_REASONING_FAMILIES:
        raise EngineeringReasoningError(f"unsupported model family for reasoning: {model_family}")

    registry = rule_registry or RuleRegistry.load()
    rules = registry.for_family(model_family)
    findings = _findings_from_report(knowledge_report)
    source_knowledge_report_id = _source_report_id(knowledge_report)
    rule_versions = _rule_versions_by_id(registry)

    observations = _build_observations(findings, rule_versions)
    interactions = detect_rule_interactions(rules, findings, metrics)
    tradeoffs = generate_tradeoffs(rules, findings, metrics)
    conflicts = detect_reasoning_conflicts(rules, findings, interactions, metrics)
    recommendations = generate_recommendations(rules, findings, interactions, conflicts, tradeoffs, metrics)
    high_priority_count = len([item for item in recommendations if item.priority in {"critical", "high"}])

    summary = _summary(
        observations=observations,
        interactions_count=len(interactions),
        tradeoffs_count=len(tradeoffs),
        conflicts_count=len(conflicts),
        recommendations_count=len(recommendations),
        high_priority_count=high_priority_count,
    )
    report_metadata = {
        "rule_versions": {rule.id: rule.rule_version for rule in rules},
        "parameter_names": sorted(parameters.keys()) if isinstance(parameters, dict) else [],
        "has_metrics": bool(metrics),
        "has_feature_recognition_report": feature_recognition_report is not None,
    }
    if metadata:
        report_metadata.update(metadata)

    report_data = {
        "report_id": "pending",
        "timestamp": timestamp or datetime.now().astimezone().isoformat(),
        "model_family": model_family,
        "reasoning_version": REASONING_ENGINE_VERSION,
        "source_knowledge_report_id": source_knowledge_report_id,
        "observations": [item.model_dump(mode="json") for item in observations],
        "interactions": [item.model_dump(mode="json") for item in interactions],
        "tradeoffs": [item.model_dump(mode="json") for item in tradeoffs],
        "conflicts": [item.model_dump(mode="json") for item in conflicts],
        "recommendations": [item.model_dump(mode="json") for item in recommendations],
        "summary": summary,
        "limitations": list(DEFAULT_REASONING_LIMITATIONS),
        "metadata": report_metadata,
    }
    report_data["report_id"] = make_reasoning_report_id(report_data)
    return EngineeringReasoningReport.model_validate(report_data)


def write_engineering_reasoning_report(report: EngineeringReasoningReport, path: str | Path) -> Path:
    """Write an engineering reasoning report as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_json(), encoding="utf-8")
    return output_path
