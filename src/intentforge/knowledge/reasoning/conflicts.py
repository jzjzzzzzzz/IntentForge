"""Deterministic conflict detection for engineering reasoning."""

from __future__ import annotations

from typing import Any

from intentforge.knowledge.schema import DesignKnowledgeRule, KnowledgeFinding
from intentforge.knowledge.reasoning.schema import ReasoningConflict, RuleInteraction, stable_digest


def _failed_ids(findings: list[KnowledgeFinding]) -> set[str]:
    return {finding.rule_id for finding in findings if not finding.passed}


def _rule_map(rules: list[DesignKnowledgeRule]) -> dict[str, DesignKnowledgeRule]:
    return {rule.id: rule for rule in rules}


def _confidence(rule_ids: list[str], rules_by_id: dict[str, DesignKnowledgeRule]) -> float:
    values = [rules_by_id[rule_id].confidence for rule_id in rule_ids if rule_id in rules_by_id]
    return round(min(values), 4) if values else 0.5


def _add_conflict(
    conflicts: dict[str, ReasoningConflict],
    *,
    rule_ids: list[str],
    description: str,
    conflict_type: str,
    resolution_strategy: str,
    severity: str,
    rules_by_id: dict[str, DesignKnowledgeRule],
) -> None:
    stable_rule_ids = sorted(dict.fromkeys(rule_ids))
    if len(stable_rule_ids) < 2:
        return
    conflict_id = stable_digest("conflict", {"rule_ids": stable_rule_ids, "type": conflict_type})
    if conflict_id in conflicts:
        return
    conflicts[conflict_id] = ReasoningConflict(
        conflict_id=conflict_id,
        rule_ids=stable_rule_ids,
        description=description,
        conflict_type=conflict_type,  # type: ignore[arg-type]
        resolution_strategy=resolution_strategy,
        severity=severity,
        confidence=_confidence(stable_rule_ids, rules_by_id),
    )


def detect_reasoning_conflicts(
    rules: list[DesignKnowledgeRule],
    findings: list[KnowledgeFinding],
    interactions: list[RuleInteraction],
    metrics: dict[str, Any] | None = None,
) -> list[ReasoningConflict]:
    """Detect advisory conflicts supported by findings and metadata."""

    del metrics
    failed = _failed_ids(findings)
    rules_by_id = _rule_map(rules)
    conflicts: dict[str, ReasoningConflict] = {}

    if {"hole_edge_margin_001", "hole_spacing_001"} <= failed:
        _add_conflict(
            conflicts,
            rule_ids=["hole_edge_margin_001", "hole_spacing_001"],
            description=(
                "Hole edge margin and hole spacing are both below recommendation. "
                "Changing one spacing dimension inside a fixed plate envelope can make the other worse."
            ),
            conflict_type="geometry_constraint_conflict",
            resolution_strategy="Increase the plate envelope before reducing hole spacing or moving holes inward.",
            severity="warning",
            rules_by_id=rules_by_id,
        )

    if "gusset_recommendation_001" in failed and (
        "cutout_stiffness_tradeoff_001" in failed or "thin_section_warning_001" in failed
    ):
        supporting = ["gusset_recommendation_001"]
        if "cutout_stiffness_tradeoff_001" in failed:
            supporting.append("cutout_stiffness_tradeoff_001")
        if "thin_section_warning_001" in failed:
            supporting.append("thin_section_warning_001")
        _add_conflict(
            conflicts,
            rule_ids=supporting,
            description=(
                "A stiffness-improvement recommendation and material-removal concern are active together."
            ),
            conflict_type="recommendation_conflict",
            resolution_strategy="Review whether stiffness intent should take priority over mass or cutout simplification.",
            severity="warning",
            rules_by_id=rules_by_id,
        )

    if "manufacturing_simplicity_001" in failed:
        optional_rule_ids = [
            rule_id
            for rule_id in ("corner_radius_001", "gusset_recommendation_001", "cutout_stiffness_tradeoff_001")
            if rule_id in failed
        ]
        if optional_rule_ids:
            _add_conflict(
                conflicts,
                rule_ids=["manufacturing_simplicity_001", *optional_rule_ids],
                description=(
                    "The design may be geometrically valid while optional features increase manufacturing complexity."
                ),
                conflict_type="recommendation_conflict",
                resolution_strategy="Keep optional features only when they are required by design intent or validation findings.",
                severity="recommendation",
                rules_by_id=rules_by_id,
            )

    if "fastener_accessibility_001" in failed and (
        "hole_edge_margin_001" in failed or "tool_clearance_001" in failed
    ):
        supporting = ["fastener_accessibility_001"]
        if "hole_edge_margin_001" in failed:
            supporting.append("hole_edge_margin_001")
        if "tool_clearance_001" in failed:
            supporting.append("tool_clearance_001")
        _add_conflict(
            conflicts,
            rule_ids=supporting,
            description=(
                "Fastener accessibility is limited by nearby geometry or clearance constraints."
            ),
            conflict_type="geometry_constraint_conflict",
            resolution_strategy="Increase clearance around fasteners before treating the hole layout as assembly-ready.",
            severity="recommendation",
            rules_by_id=rules_by_id,
        )

    for interaction in interactions:
        if interaction.interaction_type != "conflicts":
            continue
        _add_conflict(
            conflicts,
            rule_ids=interaction.rule_ids,
            description=interaction.description,
            conflict_type="recommendation_conflict",
            resolution_strategy=interaction.effect,
            severity="warning",
            rules_by_id=rules_by_id,
        )

    return sorted(conflicts.values(), key=lambda item: item.conflict_id)
