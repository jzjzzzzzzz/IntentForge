from __future__ import annotations

from intentforge.knowledge import RuleRegistry, make_knowledge_report
from intentforge.knowledge.reasoning import build_engineering_reasoning_report
from intentforge.knowledge.schema import KnowledgeFinding


FIXED_TIMESTAMP = "2026-07-10T00:00:00+00:00"


def registry() -> RuleRegistry:
    return RuleRegistry.load()


def finding(rule_id: str, *, passed: bool = False) -> KnowledgeFinding:
    rule = registry().get(rule_id)
    return KnowledgeFinding(
        rule_id=rule.id,
        rule_name=rule.name,
        category=rule.category,
        severity=rule.severity,
        passed=passed,
        message=f"{rule.name} passed." if passed else rule.description,
        recommendation=rule.recommendation,
        confidence=rule.confidence,
        metadata={"rule_version": rule.rule_version},
    )


def reasoning_report(
    failed_rule_ids: list[str],
    *,
    model_family: str = "wall_mounted_bracket",
    passed_rule_ids: list[str] | None = None,
):
    findings = [finding(rule_id, passed=False) for rule_id in failed_rule_ids]
    findings.extend(finding(rule_id, passed=True) for rule_id in (passed_rule_ids or []))
    reg = registry()
    knowledge_report = make_knowledge_report(findings, rules_checked=reg.count(), timestamp=FIXED_TIMESTAMP)
    return build_engineering_reasoning_report(
        model_family=model_family,
        knowledge_report=knowledge_report,
        rule_registry=reg,
        timestamp=FIXED_TIMESTAMP,
    )
