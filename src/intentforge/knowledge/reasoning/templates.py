"""Markdown rendering for deterministic engineering reasoning reports."""

from __future__ import annotations

from pathlib import Path

from intentforge.knowledge.reasoning.schema import EngineeringReasoningReport


def _rule_label(rule_id: str, report: EngineeringReasoningReport) -> str:
    versions = report.metadata.get("rule_versions", {}) if isinstance(report.metadata, dict) else {}
    version = versions.get(rule_id)
    return f"{rule_id} v{version}" if version else rule_id


def render_engineering_reasoning_markdown(report: EngineeringReasoningReport) -> str:
    """Render a stable human-readable engineering reasoning report."""

    lines = [
        "# Engineering Reasoning Report",
        "",
        "## Summary",
        f"- Model family: {report.model_family}",
        f"- Reasoning engine version: {report.reasoning_version}",
        f"- Source knowledge report: {report.source_knowledge_report_id}",
        f"- Findings analyzed: {report.summary.get('findings_analyzed', 0)}",
        f"- Conflicts: {report.summary.get('conflicts', 0)}",
        f"- Trade-offs: {report.summary.get('tradeoffs', 0)}",
        f"- High-priority recommendations: {report.summary.get('high_priority_recommendations', 0)}",
        "",
        "## Key Observations",
    ]

    failed_observations = [step for step in report.observations if step.evidence.get("passed") is False]
    if failed_observations:
        for step in failed_observations:
            rules = ", ".join(_rule_label(rule_id, report) for rule_id in step.rule_ids)
            lines.append(f"- {step.statement} (rules: {rules}, confidence: {step.confidence:.2f})")
    else:
        lines.append("- No advisory findings were triggered by the evaluated knowledge rules.")

    lines.extend(["", "## Rule Interactions"])
    if report.interactions:
        for interaction in report.interactions:
            rules = ", ".join(_rule_label(rule_id, report) for rule_id in interaction.rule_ids)
            lines.extend(
                [
                    f"- Type: {interaction.interaction_type}",
                    f"  Rules: {rules}",
                    f"  Interaction: {interaction.description}",
                    f"  Effect: {interaction.effect}",
                    f"  Confidence: {interaction.confidence:.2f}",
                ]
            )
    else:
        lines.append("- No rule interactions were detected from the current findings.")

    lines.extend(["", "## Trade-offs"])
    if report.tradeoffs:
        for tradeoff in report.tradeoffs:
            rules = ", ".join(_rule_label(rule_id, report) for rule_id in tradeoff.source_rule_ids)
            lines.extend(
                [
                    f"- Rules: {rules}",
                    f"  Benefit: {tradeoff.benefit}",
                    f"  Cost: {tradeoff.cost}",
                    f"  Affected parameters: {', '.join(tradeoff.affected_parameters) if tradeoff.affected_parameters else 'not specified'}",
                    f"  Confidence: {tradeoff.confidence:.2f}",
                ]
            )
    else:
        lines.append("- No trade-offs were generated for this design.")

    lines.extend(["", "## Conflicts"])
    if report.conflicts:
        for conflict in report.conflicts:
            rules = ", ".join(_rule_label(rule_id, report) for rule_id in conflict.rule_ids)
            lines.extend(
                [
                    f"- Type: {conflict.conflict_type}",
                    f"  Rules: {rules}",
                    f"  Description: {conflict.description}",
                    f"  Resolution strategy: {conflict.resolution_strategy}",
                    f"  Confidence: {conflict.confidence:.2f}",
                ]
            )
    else:
        lines.append("- No recommendation conflicts were detected.")

    lines.extend(["", "## Priority Recommendations"])
    if report.recommendations:
        for recommendation in report.recommendations:
            rules = ", ".join(_rule_label(rule_id, report) for rule_id in recommendation.rule_ids)
            lines.extend(
                [
                    f"- Priority: {recommendation.priority.upper()}",
                    f"  Action: {recommendation.action}",
                    f"  Rules: {rules}",
                    f"  Reason: {recommendation.reason}",
                    f"  Expected effect: {recommendation.expected_effect}",
                    f"  Affected parameters: {', '.join(recommendation.affected_parameters) if recommendation.affected_parameters else 'not specified'}",
                    f"  Confidence: {recommendation.confidence:.2f}",
                ]
            )
    else:
        lines.append("- No corrective recommendations were generated.")

    lines.extend(["", "## Limitations"])
    for limitation in report.limitations:
        lines.append(f"- {limitation}")
    lines.append("")
    return "\n".join(lines)


def write_engineering_reasoning_markdown(report: EngineeringReasoningReport, path: str | Path) -> Path:
    """Write a Markdown reasoning report."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_engineering_reasoning_markdown(report), encoding="utf-8")
    return output_path
