"""Focused deterministic benchmark for engineering reasoning behavior."""

from __future__ import annotations

from typing import Any

from intentforge.knowledge.report import make_knowledge_report
from intentforge.knowledge.rules import RuleRegistry
from intentforge.knowledge.schema import DesignKnowledgeRule, KnowledgeFinding
from intentforge.knowledge.reasoning.engine import build_engineering_reasoning_report


def _finding(rule: DesignKnowledgeRule, *, passed: bool) -> KnowledgeFinding:
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


def _case_definitions() -> list[dict[str, Any]]:
    return [
        {
            "id": "reasoning_001_valid_wall",
            "model_family": "wall_mounted_bracket",
            "failed_rules": [],
            "passed_rules": ["hole_edge_margin_001", "hole_spacing_001"],
            "expected_interaction_type": None,
            "expected_conflict": False,
            "expected_priority": None,
        },
        {
            "id": "reasoning_002_edge_margin",
            "model_family": "wall_mounted_bracket",
            "failed_rules": ["hole_edge_margin_001"],
            "expected_interaction_type": None,
            "expected_conflict": False,
            "expected_priority": "high",
            "expected_recommendation_contains": "plate width",
        },
        {
            "id": "reasoning_003_hole_spacing",
            "model_family": "wall_mounted_bracket",
            "failed_rules": ["hole_spacing_001"],
            "expected_interaction_type": None,
            "expected_conflict": False,
            "expected_priority": "high",
            "expected_recommendation_contains": "design envelope",
        },
        {
            "id": "reasoning_004_edge_and_spacing",
            "model_family": "wall_mounted_bracket",
            "failed_rules": ["hole_edge_margin_001", "hole_spacing_001"],
            "expected_interaction_type": "conflicts",
            "expected_conflict": True,
            "expected_priority": "high",
            "expected_recommendation_contains": "plate width",
        },
        {
            "id": "reasoning_005_l_gusset_recommended",
            "model_family": "l_bracket",
            "failed_rules": ["gusset_recommendation_001"],
            "expected_interaction_type": None,
            "expected_conflict": False,
            "expected_priority": "low",
            "expected_recommendation_contains": "gusset",
        },
        {
            "id": "reasoning_006_l_gusset_present",
            "model_family": "l_bracket",
            "failed_rules": [],
            "passed_rules": ["gusset_recommendation_001"],
            "expected_interaction_type": None,
            "expected_conflict": False,
            "expected_priority": None,
        },
        {
            "id": "reasoning_007_cutout_thin_section",
            "model_family": "wall_mounted_bracket",
            "failed_rules": ["cutout_stiffness_tradeoff_001", "thin_section_warning_001"],
            "expected_interaction_type": "reinforces",
            "expected_conflict": False,
            "expected_priority": "high",
            "expected_recommendation_contains": "cutout",
        },
        {
            "id": "reasoning_008_manufacturing_complexity",
            "model_family": "l_bracket",
            "failed_rules": ["manufacturing_simplicity_001", "corner_radius_001"],
            "expected_interaction_type": "conflicts",
            "expected_conflict": True,
            "expected_priority": "medium",
            "expected_recommendation_contains": "optional",
        },
        {
            "id": "reasoning_009_fastener_access",
            "model_family": "wall_mounted_bracket",
            "failed_rules": ["fastener_accessibility_001", "hole_edge_margin_001"],
            "expected_interaction_type": "depends_on",
            "expected_conflict": True,
            "expected_priority": "high",
            "expected_recommendation_contains": "clearance",
        },
        {
            "id": "reasoning_010_plate_size_conflict",
            "model_family": "wall_mounted_bracket",
            "failed_rules": ["hole_edge_margin_001", "hole_spacing_001", "fastener_accessibility_001"],
            "expected_interaction_type": "conflicts",
            "expected_conflict": True,
            "expected_priority": "high",
            "expected_recommendation_contains": "plate width",
        },
    ]


def _run_case(case: dict[str, Any], registry: RuleRegistry) -> dict[str, Any]:
    rules_by_id = {rule.id: rule for rule in registry.rules}
    findings = [_finding(rules_by_id[rule_id], passed=False) for rule_id in case.get("failed_rules", [])]
    findings.extend(_finding(rules_by_id[rule_id], passed=True) for rule_id in case.get("passed_rules", []))
    knowledge_report = make_knowledge_report(
        findings,
        rules_checked=registry.count(),
        timestamp="2026-07-10T00:00:00+00:00",
    )
    report = build_engineering_reasoning_report(
        model_family=case["model_family"],
        knowledge_report=knowledge_report,
        rule_registry=registry,
        timestamp="2026-07-10T00:00:00+00:00",
    )
    repeat = build_engineering_reasoning_report(
        model_family=case["model_family"],
        knowledge_report=knowledge_report,
        rule_registry=registry,
        timestamp="2026-07-10T00:00:00+00:00",
    )

    failures: list[str] = []
    expected_interaction = case.get("expected_interaction_type")
    if expected_interaction and expected_interaction not in {item.interaction_type for item in report.interactions}:
        failures.append(f"missing interaction type {expected_interaction}")
    if case.get("expected_conflict") and not report.conflicts:
        failures.append("expected conflict was not generated")
    if not case.get("expected_conflict") and report.conflicts:
        failures.append("unexpected conflict was generated")
    expected_priority = case.get("expected_priority")
    if expected_priority:
        priorities = {item.priority for item in report.recommendations}
        if expected_priority not in priorities:
            failures.append(f"missing priority {expected_priority}")
    if case.get("expected_recommendation_contains"):
        expected_text = case["expected_recommendation_contains"].lower()
        all_actions = " ".join(item.action.lower() for item in report.recommendations)
        if expected_text not in all_actions:
            failures.append(f"recommendation missing text: {expected_text}")
    if report.report_id != repeat.report_id:
        failures.append("report id is not deterministic")

    known_rule_ids = {rule.id for rule in registry.rules}
    referenced_rule_ids = set()
    for collection_name in ("observations", "interactions", "conflicts", "recommendations"):
        for item in getattr(report, collection_name):
            referenced_rule_ids.update(getattr(item, "rule_ids", []))
    for tradeoff in report.tradeoffs:
        referenced_rule_ids.update(tradeoff.source_rule_ids)
    unknown_rule_ids = sorted(referenced_rule_ids - known_rule_ids)
    if unknown_rule_ids:
        failures.append(f"unknown rule ids: {', '.join(unknown_rule_ids)}")

    recommendation_ids = [item.recommendation_id for item in report.recommendations]
    duplicate_recommendations = len(recommendation_ids) - len(set(recommendation_ids))
    if duplicate_recommendations:
        failures.append("duplicate recommendation ids")
    if not report.limitations:
        failures.append("report limitations missing")

    return {
        "id": case["id"],
        "passed": not failures,
        "failures": failures,
        "report_id": report.report_id,
        "interaction_types": [item.interaction_type for item in report.interactions],
        "conflict_count": len(report.conflicts),
        "recommendation_priorities": [item.priority for item in report.recommendations],
        "unknown_rule_reference_count": len(unknown_rule_ids),
        "duplicate_recommendation_count": duplicate_recommendations,
        "missing_limitation_count": 0 if report.limitations else 1,
    }


def run_reasoning_benchmark(rule_registry: RuleRegistry | None = None) -> dict[str, Any]:
    """Run the focused reasoning benchmark."""

    registry = rule_registry or RuleRegistry.load()
    case_results = [_run_case(case, registry) for case in _case_definitions()]
    failed_cases = [case for case in case_results if not case["passed"]]
    return {
        "total_cases": len(case_results),
        "passed": len(case_results) - len(failed_cases),
        "failed": len(failed_cases),
        "pass_rate": (len(case_results) - len(failed_cases)) / len(case_results),
        "cases": case_results,
        "failed_cases": failed_cases,
        "unknown_rule_reference_count": sum(case["unknown_rule_reference_count"] for case in case_results),
        "duplicate_recommendation_count": sum(case["duplicate_recommendation_count"] for case in case_results),
        "missing_limitation_count": sum(case["missing_limitation_count"] for case in case_results),
    }
