"""Stable JSON report schema for engineering knowledge evaluation."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from intentforge.knowledge.schema import KnowledgeFinding


class KnowledgeReport(BaseModel):
    """Serializable report for deterministic engineering knowledge findings."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    report_id: str
    timestamp: str
    rules_checked: int
    findings: list[KnowledgeFinding] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def make_knowledge_report(
    findings: list[KnowledgeFinding],
    *,
    rules_checked: int,
    timestamp: str | None = None,
) -> KnowledgeReport:
    """Build a stable knowledge report from findings."""

    report_timestamp = timestamp or datetime.now().astimezone().isoformat()
    finding_data = [finding.model_dump(mode="json") for finding in findings]
    failed = [finding for finding in findings if not finding.passed]
    by_severity: dict[str, int] = {}
    for finding in findings:
        by_severity[finding.severity] = by_severity.get(finding.severity, 0) + 1
    identity_payload = {
        "rules_checked": rules_checked,
        "findings": [
            {
                "rule_id": finding.rule_id,
                "rule_version": finding.metadata.get("rule_version"),
                "passed": finding.passed,
                "severity": finding.severity,
            }
            for finding in findings
        ],
    }
    report_id = hashlib.sha256(json.dumps(identity_payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return KnowledgeReport(
        report_id=report_id,
        timestamp=report_timestamp,
        rules_checked=rules_checked,
        findings=findings,
        summary={
            "passed": len(findings) - len(failed),
            "failed": len(failed),
            "by_severity": by_severity,
            "advisory_findings": len(failed),
        },
    )


def write_knowledge_report(report: KnowledgeReport, path: str | Path) -> Path:
    """Write a knowledge report as JSON."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_json(), encoding="utf-8")
    return output_path
