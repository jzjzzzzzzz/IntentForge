"""Deterministic rule interaction detection for engineering reasoning."""

from __future__ import annotations

from typing import Any

from intentforge.knowledge.schema import DesignKnowledgeRule, KnowledgeFinding
from intentforge.knowledge.reasoning.schema import RuleInteraction, stable_digest


def _failed_findings(findings: list[KnowledgeFinding]) -> dict[str, KnowledgeFinding]:
    return {finding.rule_id: finding for finding in findings if not finding.passed}


def _finding_map(findings: list[KnowledgeFinding]) -> dict[str, KnowledgeFinding]:
    return {finding.rule_id: finding for finding in findings}


def _rule_map(rules: list[DesignKnowledgeRule]) -> dict[str, DesignKnowledgeRule]:
    return {rule.id: rule for rule in rules}


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _confidence_for(rule_ids: list[str], rules_by_id: dict[str, DesignKnowledgeRule]) -> float:
    confidences = [rules_by_id[rule_id].confidence for rule_id in rule_ids if rule_id in rules_by_id]
    if not confidences:
        return 0.5
    return round(min(confidences), 4)


def _add_interaction(
    interactions: dict[tuple[str, tuple[str, ...], str], RuleInteraction],
    *,
    interaction_type: str,
    rule_ids: list[str],
    description: str,
    effect: str,
    rules_by_id: dict[str, DesignKnowledgeRule],
    metadata: dict[str, Any] | None = None,
) -> None:
    stable_rule_ids = sorted(dict.fromkeys(rule_ids))
    if not stable_rule_ids:
        return
    key = (interaction_type, tuple(stable_rule_ids), effect)
    if key in interactions:
        return
    interaction_id = stable_digest(
        f"interaction_{interaction_type}",
        {"rule_ids": stable_rule_ids, "effect": effect},
    )
    interactions[key] = RuleInteraction(
        interaction_id=interaction_id,
        rule_ids=stable_rule_ids,
        interaction_type=interaction_type,  # type: ignore[arg-type]
        description=description,
        effect=effect,
        confidence=_confidence_for(stable_rule_ids, rules_by_id),
        metadata=metadata or {},
    )


def detect_rule_interactions(
    rules: list[DesignKnowledgeRule],
    findings: list[KnowledgeFinding],
    metrics: dict[str, Any] | None = None,
) -> list[RuleInteraction]:
    """Detect supported rule interactions using only explicit rule metadata."""

    del metrics
    rules_by_id = _rule_map(rules)
    all_findings = _finding_map(findings)
    failed = _failed_findings(findings)
    interactions: dict[tuple[str, tuple[str, ...], str], RuleInteraction] = {}

    for rule in sorted(rules, key=lambda item: item.id):
        reasoning = rule.reasoning or {}
        if rule.id not in all_findings:
            continue

        source_failed = rule.id in failed
        implications = _as_string_list(reasoning.get("implications"))
        default_description = implications[0] if implications else rule.description

        for target_id in _as_string_list(reasoning.get("reinforces")):
            if source_failed and target_id in failed:
                _add_interaction(
                    interactions,
                    interaction_type="reinforces",
                    rule_ids=[rule.id, target_id],
                    description=(
                        "The findings reinforce the same engineering concern; "
                        f"{default_description}"
                    ),
                    effect="reinforced engineering concern should receive higher review priority",
                    rules_by_id=rules_by_id,
                    metadata={"source": "reasoning.reinforces"},
                )

        for target_id in _as_string_list(reasoning.get("can_conflict_with")):
            if source_failed and target_id in failed:
                _add_interaction(
                    interactions,
                    interaction_type="conflicts",
                    rule_ids=[rule.id, target_id],
                    description=(
                        "The recommendations may compete within the available design envelope."
                    ),
                    effect=reasoning.get("mitigation", "review both recommendations before changing parameters"),
                    rules_by_id=rules_by_id,
                    metadata={"source": "reasoning.can_conflict_with"},
                )

        for target_id in _as_string_list(reasoning.get("depends_on")):
            if source_failed and target_id in all_findings:
                _add_interaction(
                    interactions,
                    interaction_type="depends_on",
                    rule_ids=[rule.id, target_id],
                    description="This finding depends on another design condition or clearance rule.",
                    effect="resolve the dependency before treating this recommendation as isolated",
                    rules_by_id=rules_by_id,
                    metadata={"source": "reasoning.depends_on"},
                )

        for target_id in _as_string_list(reasoning.get("duplicates")):
            if source_failed and target_id in failed:
                _add_interaction(
                    interactions,
                    interaction_type="duplicates",
                    rule_ids=[rule.id, target_id],
                    description="These findings cover overlapping engineering concerns.",
                    effect="merge duplicate recommendations during prioritization",
                    rules_by_id=rules_by_id,
                    metadata={"source": "reasoning.duplicates"},
                )

        for target_id in _as_string_list(reasoning.get("mitigates")):
            if target_id in failed:
                _add_interaction(
                    interactions,
                    interaction_type="mitigates",
                    rule_ids=[rule.id, target_id],
                    description="One recommendation may reduce the concern raised by another rule.",
                    effect=reasoning.get("mitigation", "apply the mitigation only after validating the updated design"),
                    rules_by_id=rules_by_id,
                    metadata={"source": "reasoning.mitigates"},
                )

        for target_id in _as_string_list(reasoning.get("mitigated_by")):
            if source_failed and target_id in rules_by_id:
                _add_interaction(
                    interactions,
                    interaction_type="mitigates",
                    rule_ids=[rule.id, target_id],
                    description="This finding has an encoded mitigation rule or feature.",
                    effect=reasoning.get("mitigation", "apply the mitigation only after validating the updated design"),
                    rules_by_id=rules_by_id,
                    metadata={"source": "reasoning.mitigated_by"},
                )

    failed_rules = sorted((rules_by_id[rule_id] for rule_id in failed if rule_id in rules_by_id), key=lambda item: item.id)
    for index, left in enumerate(failed_rules):
        left_affects = set(_as_string_list(left.reasoning.get("affects")))
        if not left_affects:
            continue
        for right in failed_rules[index + 1 :]:
            right_affects = set(_as_string_list(right.reasoning.get("affects")))
            overlap = sorted(left_affects & right_affects)
            if not overlap:
                continue
            _add_interaction(
                interactions,
                interaction_type="affects",
                rule_ids=[left.id, right.id],
                description=f"Both findings affect: {', '.join(overlap)}.",
                effect="coordinate parameter changes so one fix does not invalidate another intent",
                rules_by_id=rules_by_id,
                metadata={"source": "reasoning.affects", "affected_parameters": overlap},
            )

    return sorted(interactions.values(), key=lambda item: (item.interaction_type, item.interaction_id))
