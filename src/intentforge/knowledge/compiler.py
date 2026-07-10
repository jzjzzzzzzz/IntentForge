"""Compiler from human design knowledge rules to machine constraints."""

from __future__ import annotations

from collections.abc import Iterable

from intentforge.knowledge.schema import CompiledConstraint, DesignKnowledgeRule


def compile_rule(rule: DesignKnowledgeRule) -> CompiledConstraint:
    """Compile one design knowledge rule into a machine-readable constraint."""

    return CompiledConstraint(
        rule_id=rule.id,
        expression=rule.condition["expression"].strip(),
        source="engineering_rule",
        confidence=rule.confidence,
    )


def compile_rules(rules: Iterable[DesignKnowledgeRule]) -> list[CompiledConstraint]:
    """Compile multiple design knowledge rules in deterministic order."""

    return [compile_rule(rule) for rule in rules]
