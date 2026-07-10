"""Deterministic priority scoring for engineering recommendations."""

from __future__ import annotations

from intentforge.knowledge.schema import DesignKnowledgeRule, KnowledgeFinding
from intentforge.knowledge.reasoning.schema import (
    PRIORITY_RANK,
    ReasoningConflict,
    RuleInteraction,
)


SEVERITY_SCORE = {
    "error": 100.0,
    "warning": 60.0,
    "recommendation": 20.0,
    "info": 20.0,
    "pass": 0.0,
}


def priority_weight(rule: DesignKnowledgeRule | None) -> float:
    """Return a validated priority weight from rule reasoning metadata."""

    if rule is None:
        return 0.5
    value = rule.reasoning.get("priority_weight", 0.5)
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def score_finding(
    finding: KnowledgeFinding,
    rule: DesignKnowledgeRule | None,
    interactions: list[RuleInteraction] | None = None,
    conflicts: list[ReasoningConflict] | None = None,
) -> float:
    """Score a finding with a stable transparent formula.

    Formula:
    - severity: error=100, warning=60, recommendation/info=20, pass=0
    - confidence contribution: confidence * 20
    - rule priority weight contribution: priority_weight * 20
    - reinforcing interaction participation: +10 each
    - conflict participation: +10 each
    - mitigated finding participation: -5 each
    """

    if finding.passed:
        return 0.0
    score = SEVERITY_SCORE.get(finding.severity, 20.0)
    score += finding.confidence * 20.0
    score += priority_weight(rule) * 20.0

    for interaction in interactions or []:
        if finding.rule_id not in interaction.rule_ids:
            continue
        if interaction.interaction_type == "reinforces":
            score += 10.0
        elif interaction.interaction_type == "conflicts":
            score += 10.0
        elif interaction.interaction_type == "mitigates":
            score -= 5.0

    for conflict in conflicts or []:
        if finding.rule_id in conflict.rule_ids:
            score += 10.0

    return round(max(0.0, score), 4)


def priority_from_score(score: float) -> str:
    """Map a deterministic score to a recommendation priority."""

    if score >= 140.0:
        return "critical"
    if score >= 85.0:
        return "high"
    if score >= 55.0:
        return "medium"
    if score >= 25.0:
        return "low"
    return "informational"


def priority_sort_key(priority: str) -> int:
    """Sort priority values from highest to lowest importance."""

    return PRIORITY_RANK.get(priority, PRIORITY_RANK["informational"])
