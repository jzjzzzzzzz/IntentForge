"""Deterministic engineering trade-off generation."""

from __future__ import annotations

from typing import Any

from intentforge.knowledge.schema import DesignKnowledgeRule, KnowledgeFinding
from intentforge.knowledge.reasoning.schema import EngineeringTradeoff, stable_digest


def _finding_by_rule(findings: list[KnowledgeFinding]) -> dict[str, KnowledgeFinding]:
    return {finding.rule_id: finding for finding in findings}


def _is_relevant(finding: KnowledgeFinding | None) -> bool:
    if finding is None:
        return False
    return not finding.passed


def _tradeoff_confidence(rule: DesignKnowledgeRule, tradeoff: dict[str, Any]) -> float:
    raw_confidence = tradeoff.get("confidence", rule.confidence)
    try:
        return round(max(0.0, min(1.0, float(raw_confidence))), 4)
    except (TypeError, ValueError):
        return rule.confidence


def generate_tradeoffs(
    rules: list[DesignKnowledgeRule],
    findings: list[KnowledgeFinding],
    metrics: dict[str, Any] | None = None,
) -> list[EngineeringTradeoff]:
    """Generate trade-offs only for relevant evaluated findings."""

    del metrics
    findings_by_rule = _finding_by_rule(findings)
    tradeoffs: list[EngineeringTradeoff] = []
    seen_ids: set[str] = set()

    for rule in sorted(rules, key=lambda item: item.id):
        finding = findings_by_rule.get(rule.id)
        if not _is_relevant(finding):
            continue
        for index, raw_tradeoff in enumerate(rule.reasoning.get("tradeoffs", []) or []):
            if not isinstance(raw_tradeoff, dict):
                continue
            benefit = raw_tradeoff.get("benefit")
            cost = raw_tradeoff.get("cost")
            if not isinstance(benefit, str) or not benefit.strip():
                continue
            if not isinstance(cost, str) or not cost.strip():
                continue
            affected = raw_tradeoff.get("affected_parameters", [])
            if not isinstance(affected, list):
                affected = []
            affected_parameters = sorted({item for item in affected if isinstance(item, str) and item})
            tradeoff_id = stable_digest("tradeoff", {"rule_id": rule.id, "index": index, "benefit": benefit, "cost": cost})
            if tradeoff_id in seen_ids:
                continue
            seen_ids.add(tradeoff_id)
            tradeoffs.append(
                EngineeringTradeoff(
                    tradeoff_id=tradeoff_id,
                    source_rule_ids=[rule.id],
                    benefit=benefit,
                    cost=cost,
                    affected_parameters=affected_parameters,
                    severity=finding.severity if finding is not None else rule.severity,
                    confidence=_tradeoff_confidence(rule, raw_tradeoff),
                    recommendation=raw_tradeoff.get("recommendation") or rule.recommendation,
                )
            )

    return sorted(tradeoffs, key=lambda item: item.tradeoff_id)
