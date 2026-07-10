"""Focused deterministic benchmark for engineering reasoning behavior."""

from __future__ import annotations

from intentforge.knowledge.rules import RuleRegistry
from intentforge.knowledge.reasoning.verification import run_reasoning_verification


def run_reasoning_benchmark(rule_registry: RuleRegistry | None = None) -> dict:
    """Run the focused reasoning benchmark backed by golden engineering cases."""

    return run_reasoning_verification(rule_registry=rule_registry)
