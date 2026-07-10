"""Prioritized deterministic recommendation generation."""

from __future__ import annotations

from typing import Any

from intentforge.knowledge.schema import DesignKnowledgeRule, KnowledgeFinding
from intentforge.knowledge.reasoning.priorities import priority_from_score, priority_sort_key, score_finding
from intentforge.knowledge.reasoning.schema import (
    EngineeringTradeoff,
    PrioritizedRecommendation,
    ReasoningConflict,
    RuleInteraction,
    stable_digest,
)


def _rule_map(rules: list[DesignKnowledgeRule]) -> dict[str, DesignKnowledgeRule]:
    return {rule.id: rule for rule in rules}


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _affected_parameters(rule: DesignKnowledgeRule | None, tradeoffs: list[EngineeringTradeoff]) -> list[str]:
    affected = set(_as_string_list(rule.reasoning.get("affects")) if rule is not None else [])
    for tradeoff in tradeoffs:
        affected.update(tradeoff.affected_parameters)
    return sorted(affected)


def _limitations(rule: DesignKnowledgeRule | None) -> list[str]:
    default = ["This recommendation is heuristic and does not replace load-specific engineering analysis."]
    if rule is None:
        return default
    values = _as_string_list(rule.reasoning.get("limitations"))
    return values or default


def _make_recommendation_id(rule_ids: list[str], action: str) -> str:
    return stable_digest("recommendation", {"rule_ids": sorted(rule_ids), "action": action})


def _merge_recommendation(
    merged: dict[str, PrioritizedRecommendation],
    recommendation: PrioritizedRecommendation,
) -> None:
    key = recommendation.action.strip().lower()
    existing = merged.get(key)
    if existing is None:
        merged[key] = recommendation
        return

    rule_ids = sorted(set(existing.rule_ids) | set(recommendation.rule_ids))
    affected = sorted(set(existing.affected_parameters) | set(recommendation.affected_parameters))
    limitations = sorted(set(existing.limitations) | set(recommendation.limitations))
    chosen_priority = (
        recommendation.priority
        if priority_sort_key(recommendation.priority) < priority_sort_key(existing.priority)
        else existing.priority
    )
    merged[key] = PrioritizedRecommendation(
        recommendation_id=_make_recommendation_id(rule_ids, existing.action),
        rule_ids=rule_ids,
        priority=chosen_priority,
        action=existing.action,
        reason=existing.reason if existing.reason == recommendation.reason else f"{existing.reason} {recommendation.reason}",
        expected_effect=(
            existing.expected_effect
            if existing.expected_effect == recommendation.expected_effect
            else f"{existing.expected_effect} {recommendation.expected_effect}"
        ),
        affected_parameters=affected,
        confidence=round(max(existing.confidence, recommendation.confidence), 4),
        limitations=limitations,
    )


def _tradeoffs_for_rule(rule_id: str, tradeoffs: list[EngineeringTradeoff]) -> list[EngineeringTradeoff]:
    return [tradeoff for tradeoff in tradeoffs if rule_id in tradeoff.source_rule_ids]


def generate_recommendations(
    rules: list[DesignKnowledgeRule],
    findings: list[KnowledgeFinding],
    interactions: list[RuleInteraction],
    conflicts: list[ReasoningConflict],
    tradeoffs: list[EngineeringTradeoff],
    metrics: dict[str, Any] | None = None,
) -> list[PrioritizedRecommendation]:
    """Generate, merge, and sort prioritized engineering recommendations."""

    del metrics
    rules_by_id = _rule_map(rules)
    merged: dict[str, PrioritizedRecommendation] = {}

    for finding in sorted(findings, key=lambda item: item.rule_id):
        if finding.passed:
            continue
        rule = rules_by_id.get(finding.rule_id)
        rule_tradeoffs = _tradeoffs_for_rule(finding.rule_id, tradeoffs)
        score = score_finding(finding, rule, interactions, conflicts)
        priority = priority_from_score(score)
        action = (
            (rule.reasoning.get("mitigation") if rule is not None else None)
            or finding.recommendation
        )
        expected_effect = finding.message
        if rule_tradeoffs:
            expected_effect = f"{expected_effect} Relevant trade-off: {rule_tradeoffs[0].benefit}"
        recommendation = PrioritizedRecommendation(
            recommendation_id=_make_recommendation_id([finding.rule_id], action),
            rule_ids=[finding.rule_id],
            priority=priority,  # type: ignore[arg-type]
            action=action,
            reason=finding.message,
            expected_effect=expected_effect,
            affected_parameters=_affected_parameters(rule, rule_tradeoffs),
            confidence=finding.confidence,
            limitations=_limitations(rule),
        )
        _merge_recommendation(merged, recommendation)

    for conflict in conflicts:
        if set(conflict.rule_ids) == {"hole_edge_margin_001", "hole_spacing_001"}:
            action = "Increase plate width before reducing hole spacing."
            recommendation = PrioritizedRecommendation(
                recommendation_id=_make_recommendation_id(conflict.rule_ids, action),
                rule_ids=conflict.rule_ids,
                priority="high",
                action=action,
                reason=conflict.description,
                expected_effect=(
                    "Provides more room to improve edge distance without further reducing hole separation."
                ),
                affected_parameters=["hole_spacing", "plate_width"],
                confidence=conflict.confidence,
                limitations=[
                    "This is an advisory spacing recommendation and does not replace load-specific analysis.",
                ],
            )
            _merge_recommendation(merged, recommendation)

    return sorted(
        merged.values(),
        key=lambda item: (priority_sort_key(item.priority), item.recommendation_id),
    )
