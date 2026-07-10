"""Markdown rationale generation for engineering knowledge findings."""

from __future__ import annotations

from intentforge.knowledge.schema import KnowledgeFinding


def generate_design_rationale(findings: list[KnowledgeFinding]) -> str:
    """Render knowledge findings as a concise Markdown rationale report."""

    lines = [
        "# Design Review",
        "",
        "This rationale is based on deterministic IntentForge engineering knowledge rules.",
        "It does not represent FEA, simulation, certification, or guaranteed safety.",
        "",
    ]
    if not findings:
        lines.extend(["## Knowledge Findings", "", "No applicable engineering knowledge findings were generated.", ""])
        return "\n".join(lines)

    for finding in findings:
        status = "PASS" if finding.passed else finding.severity.upper()
        version = finding.metadata.get("rule_version", "unknown")
        lines.extend(
            [
                f"## {status}: {finding.rule_name}",
                "",
                f"Rule: {finding.rule_id}",
                "",
                f"Version: {version}",
                "",
                f"Confidence: {finding.confidence:.2f}",
                "",
                "Reason:",
                finding.message,
                "",
                "Recommendation:",
                finding.recommendation,
                "",
            ]
        )
    return "\n".join(lines)
