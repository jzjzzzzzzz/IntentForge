"""Golden-case verification for deterministic engineering reasoning."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from intentforge.knowledge.report import make_knowledge_report
from intentforge.knowledge.rules import RuleRegistry
from intentforge.knowledge.schema import DesignKnowledgeRule, KnowledgeFinding
from intentforge.knowledge.reasoning.engine import build_engineering_reasoning_report
from intentforge.knowledge.reasoning.schema import EngineeringReasoningReport, PrioritizedRecommendation


DEFAULT_GOLDEN_CASE_RESOURCE = "golden_cases.yaml"
FIXED_VERIFICATION_TIMESTAMP = "2026-07-10T00:00:00+00:00"


class ReasoningVerificationError(ValueError):
    """Raised when golden verification data is malformed."""


def load_golden_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load packaged or user-provided golden reasoning cases."""

    if path is None:
        text = resources.files("intentforge.knowledge.reasoning.data").joinpath(
            DEFAULT_GOLDEN_CASE_RESOURCE
        ).read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    cases = raw.get("cases")
    if not isinstance(cases, list):
        raise ReasoningVerificationError("golden case data must contain a top-level cases list")
    validate_golden_cases(cases)
    return cases


def validate_golden_cases(cases: list[dict[str, Any]]) -> None:
    """Validate golden case structure before running the reasoning engine."""

    seen_ids: set[str] = set()
    required_fields = {"id", "model_family", "failed_rules", "expected_report_id"}
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ReasoningVerificationError(f"case {index} must be a mapping")
        missing = sorted(required_fields - set(case))
        if missing:
            raise ReasoningVerificationError(f"case {case.get('id', index)} missing fields: {', '.join(missing)}")
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id:
            raise ReasoningVerificationError(f"case {index} id must be a non-empty string")
        if case_id in seen_ids:
            raise ReasoningVerificationError(f"duplicate golden case id: {case_id}")
        seen_ids.add(case_id)
        for field_name in ("failed_rules", "passed_rules", "expected_interaction_types", "expected_priorities", "expected_recommendation_contains"):
            value = case.get(field_name, [])
            if value is None:
                continue
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ReasoningVerificationError(f"case {case_id}.{field_name} must be a list of strings")
        if case["model_family"] not in {"wall_mounted_bracket", "l_bracket"}:
            raise ReasoningVerificationError(f"case {case_id} has unsupported model_family")


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


def _build_findings(case: dict[str, Any], registry: RuleRegistry) -> list[KnowledgeFinding]:
    rules_by_id = {rule.id: rule for rule in registry.rules}
    findings: list[KnowledgeFinding] = []
    for rule_id in case.get("failed_rules", []):
        findings.append(_finding(rules_by_id[rule_id], passed=False))
    for rule_id in case.get("passed_rules", []):
        findings.append(_finding(rules_by_id[rule_id], passed=True))
    return findings


def _build_report(case: dict[str, Any], registry: RuleRegistry) -> EngineeringReasoningReport:
    findings = _build_findings(case, registry)
    knowledge_report = make_knowledge_report(
        findings,
        rules_checked=registry.count(),
        timestamp=FIXED_VERIFICATION_TIMESTAMP,
    )
    return build_engineering_reasoning_report(
        model_family=case["model_family"],
        knowledge_report=knowledge_report,
        rule_registry=registry,
        timestamp=FIXED_VERIFICATION_TIMESTAMP,
    )


def _direction(action: str) -> str | None:
    words = action.strip().lower().replace(".", "").split()
    if not words:
        return None
    first = words[0]
    if first in {"increase", "add", "enlarge", "widen"}:
        return "increase"
    if first in {"reduce", "decrease", "remove", "shrink", "narrow"}:
        return "decrease"
    return None


def _mentions_parameter(action: str, parameter: str) -> bool:
    normalized_action = action.strip().lower().replace("_", " ")
    normalized_parameter = parameter.strip().lower().replace("_", " ")
    tokens = [normalized_parameter]
    if normalized_parameter.endswith(" width") or normalized_parameter.endswith(" height"):
        tokens.append(normalized_parameter.rsplit(" ", 1)[0])
    if normalized_parameter.startswith("hole "):
        tokens.append(normalized_parameter.replace("hole ", ""))
    if normalized_parameter.startswith("plate "):
        tokens.append(normalized_parameter.replace("plate ", ""))
    return any(token and token in normalized_action for token in tokens)


def detect_recommendation_contradictions(
    recommendations: list[PrioritizedRecommendation],
) -> list[dict[str, Any]]:
    """Detect direct recommendation contradictions over shared parameters."""

    contradictions: list[dict[str, Any]] = []
    for left_index, left in enumerate(recommendations):
        left_direction = _direction(left.action)
        if left_direction is None:
            continue
        left_params = set(left.affected_parameters)
        if not left_params:
            continue
        for right in recommendations[left_index + 1 :]:
            right_direction = _direction(right.action)
            if right_direction is None or right_direction == left_direction:
                continue
            overlap = sorted(left_params & set(right.affected_parameters))
            overlap = [
                parameter
                for parameter in overlap
                if _mentions_parameter(left.action, parameter) and _mentions_parameter(right.action, parameter)
            ]
            if not overlap:
                continue
            contradictions.append(
                {
                    "left_recommendation_id": left.recommendation_id,
                    "right_recommendation_id": right.recommendation_id,
                    "affected_parameters": overlap,
                    "message": "recommendations move the same parameter in opposite directions",
                }
            )
    return contradictions


def _allowed_parameters_for_family(registry: RuleRegistry, family: str) -> set[str]:
    allowed: set[str] = set()
    for rule in registry.for_family(family):
        reasoning = rule.reasoning or {}
        allowed.update(item for item in reasoning.get("affects", []) if isinstance(item, str))
        for tradeoff in reasoning.get("tradeoffs", []) or []:
            if isinstance(tradeoff, dict):
                allowed.update(item for item in tradeoff.get("affected_parameters", []) if isinstance(item, str))
        allowed.update(item for item in rule.condition.get("required_metrics", []) if isinstance(item, str))
    return allowed


def validate_recommendation_applicability(
    report: EngineeringReasoningReport,
    registry: RuleRegistry,
) -> list[dict[str, Any]]:
    """Verify recommendations refer to applicable rules and known parameters."""

    applicable_rule_ids = {rule.id for rule in registry.for_family(report.model_family)}
    failed_rule_ids = {
        step.rule_ids[0]
        for step in report.observations
        if step.rule_ids and step.evidence.get("passed") is False
    }
    allowed_parameters = _allowed_parameters_for_family(registry, report.model_family)
    issues: list[dict[str, Any]] = []

    for recommendation in report.recommendations:
        unknown_rule_ids = sorted(set(recommendation.rule_ids) - applicable_rule_ids)
        if unknown_rule_ids:
            issues.append(
                {
                    "recommendation_id": recommendation.recommendation_id,
                    "message": f"recommendation references rules outside {report.model_family}",
                    "rule_ids": unknown_rule_ids,
                }
            )
        non_failed_rule_ids = sorted(set(recommendation.rule_ids) - failed_rule_ids)
        if non_failed_rule_ids:
            issues.append(
                {
                    "recommendation_id": recommendation.recommendation_id,
                    "message": "recommendation references rules that did not trigger advisory findings",
                    "rule_ids": non_failed_rule_ids,
                }
            )
        unknown_parameters = sorted(set(recommendation.affected_parameters) - allowed_parameters)
        if unknown_parameters:
            issues.append(
                {
                    "recommendation_id": recommendation.recommendation_id,
                    "message": "recommendation affects parameters not declared by applicable rule metadata",
                    "affected_parameters": unknown_parameters,
                }
            )
        if not recommendation.action.strip():
            issues.append({"recommendation_id": recommendation.recommendation_id, "message": "empty action"})
        if not recommendation.limitations:
            issues.append({"recommendation_id": recommendation.recommendation_id, "message": "missing limitations"})

    return issues


def run_golden_case(case: dict[str, Any], registry: RuleRegistry | None = None) -> dict[str, Any]:
    """Run one golden reasoning case and compare it with expected behavior."""

    active_registry = registry or RuleRegistry.load()
    report = _build_report(case, active_registry)
    repeat = _build_report(case, active_registry)
    failures: list[str] = []

    if report.report_id != repeat.report_id:
        failures.append("report id is not deterministic")
    if report.report_id != case["expected_report_id"]:
        failures.append(f"report id mismatch: expected {case['expected_report_id']}, actual {report.report_id}")

    interaction_types = [item.interaction_type for item in report.interactions]
    for expected_type in case.get("expected_interaction_types", []) or []:
        if expected_type not in interaction_types:
            failures.append(f"missing interaction type {expected_type}")
    expected_conflict_count = case.get("expected_conflict_count")
    if expected_conflict_count is not None and len(report.conflicts) != expected_conflict_count:
        failures.append(f"conflict count mismatch: expected {expected_conflict_count}, actual {len(report.conflicts)}")
    priorities = [item.priority for item in report.recommendations]
    for expected_priority in case.get("expected_priorities", []) or []:
        if expected_priority not in priorities:
            failures.append(f"missing priority {expected_priority}")
    action_text = " ".join(item.action.lower() for item in report.recommendations)
    for expected_text in case.get("expected_recommendation_contains", []) or []:
        if expected_text.lower() not in action_text:
            failures.append(f"recommendation missing text: {expected_text}")

    contradictions = detect_recommendation_contradictions(report.recommendations)
    if case.get("expected_no_contradictions", True) and contradictions:
        failures.append("recommendation contradiction detected")
    applicability_issues = validate_recommendation_applicability(report, active_registry)
    if applicability_issues:
        failures.append("recommendation applicability issue detected")

    return {
        "id": case["id"],
        "model_family": case["model_family"],
        "passed": not failures,
        "failures": failures,
        "report_id": report.report_id,
        "expected_report_id": case["expected_report_id"],
        "deterministic_report_id": report.report_id == repeat.report_id,
        "interaction_types": interaction_types,
        "conflict_count": len(report.conflicts),
        "recommendation_ids": [item.recommendation_id for item in report.recommendations],
        "recommendation_priorities": priorities,
        "contradictions": contradictions,
        "applicability_issues": applicability_issues,
        "summary": report.summary,
    }


def run_reasoning_verification(
    rule_registry: RuleRegistry | None = None,
    cases: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run deterministic golden-case verification for the reasoning engine."""

    active_registry = rule_registry or RuleRegistry.load()
    golden_cases = cases if cases is not None else load_golden_cases()
    validate_golden_cases(golden_cases)
    case_results = [run_golden_case(case, active_registry) for case in golden_cases]
    failed_cases = [case for case in case_results if not case["passed"]]
    total_cases = len(case_results)
    passed_cases = total_cases - len(failed_cases)
    contradiction_count = sum(len(case["contradictions"]) for case in case_results)
    applicability_error_count = sum(len(case["applicability_issues"]) for case in case_results)
    unknown_rule_reference_count = sum(
        len(
            [
                issue
                for issue in case["applicability_issues"]
                if issue.get("message", "").startswith("recommendation references rules outside")
            ]
        )
        for case in case_results
    )
    nondeterministic_report_count = len([case for case in case_results if not case["deterministic_report_id"]])
    report_id_mismatch_count = len([case for case in case_results if case["report_id"] != case["expected_report_id"]])

    return {
        "total_cases": total_cases,
        "passed": passed_cases,
        "failed": len(failed_cases),
        "pass_rate": passed_cases / total_cases if total_cases else 0.0,
        "cases": case_results,
        "passed_cases": [case for case in case_results if case["passed"]],
        "failed_cases": failed_cases,
        "contradiction_count": contradiction_count,
        "applicability_error_count": applicability_error_count,
        "nondeterministic_report_count": nondeterministic_report_count,
        "report_id_mismatch_count": report_id_mismatch_count,
        "unknown_rule_reference_count": unknown_rule_reference_count,
        "duplicate_recommendation_count": sum(
            len(case["recommendation_ids"]) - len(set(case["recommendation_ids"])) for case in case_results
        ),
        "missing_limitation_count": sum(
            len(
                [
                    issue
                    for issue in case["applicability_issues"]
                    if issue.get("message") == "missing limitations"
                ]
            )
            for case in case_results
        ),
    }
