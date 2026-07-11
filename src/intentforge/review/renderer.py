"""Deterministic Markdown rendering for engineering review decisions."""

from __future__ import annotations

from intentforge.review.schema import ReviewDecision


DECISION_LANGUAGE = {
    "accepted_within_declared_scope": "Accepted within the declared IntentForge scope.",
    "accepted_with_conditions": "Accepted with explicit conditions within the declared IntentForge scope.",
    "manual_review_required": "Manual review is required before this record can satisfy the selected policy.",
    "rejected_by_policy": "Rejected by the selected policy.",
    "unresolved": "Unresolved because required observations or checks were unavailable.",
}


def render_review_decision_markdown(decision: ReviewDecision | dict) -> str:
    record = decision if isinstance(decision, ReviewDecision) else ReviewDecision.model_validate(decision)
    safe_rejection = record.subject_type == "safe_rejection"
    lines = [
        "# IntentForge Engineering Review Decision",
        "",
        "## Review Summary",
        DECISION_LANGUAGE[record.decision_status],
    ]
    if safe_rejection and record.decision_status == "accepted_within_declared_scope":
        lines.append("Safe rejection handling passed policy. The requested unsupported design remains rejected.")
    lines.extend([
        "",
        "## Policy Applied",
        f"- Policy: {record.policy_id}",
        f"- Version: {record.policy_version}",
        f"- Policy content ID: {record.policy_content_id}",
        "",
        "## Subject and Scope",
        f"- Subject type: {record.subject_type}",
        f"- CAD family: {record.cad_family}",
        f"- Operation: {record.operation}",
        "",
        "## Assurance Profile",
        f"- Profile: {record.assurance_profile}",
        f"- Assurance case: {record.assurance_case_id}",
        "",
        "## Final Decision",
        f"**{record.decision_status}**",
        "",
        "## Checks Passed",
    ])
    passed = [finding for finding in record.findings if finding.status == "passed"]
    lines.extend(f"- {finding.title}: {finding.summary}" for finding in passed)
    if not passed:
        lines.append("- None.")
    lines.extend(["", "## Blocking Findings"])
    blocking = [
        finding for finding in record.findings
        if finding.severity == "blocking" and finding.status in {"failed", "unresolved", "not_checked"}
    ]
    lines.extend(f"- {finding.status.upper()}: {finding.title}. {finding.summary}" for finding in blocking)
    if not blocking:
        lines.append("- None.")
    lines.extend(["", "## Manual Review Findings"])
    manual = [
        finding for finding in record.findings
        if finding.severity == "manual_review" and finding.status in {"failed", "unresolved", "not_checked"}
    ]
    lines.extend(f"- {finding.title}: {finding.summary}" for finding in manual)
    if not manual:
        lines.append("- None.")
    lines.extend(["", "## Conditions"])
    lines.extend(
        f"- {condition.title}: {condition.required_action} (type: {condition.condition_type})"
        for condition in record.conditions
    )
    if not record.conditions:
        lines.append("- None.")
    lines.extend([
        "",
        "## Claims Evaluated",
        f"- Referenced claims: {len({item for finding in record.findings for item in finding.claim_ids})}",
        "",
        "## Validation Observations",
        f"- Referenced validations: {len({item for finding in record.findings for item in finding.validation_ids})}",
        "",
        "## Capability and Evidence References",
        f"- Capabilities: {len(record.relevant_capability_ids)}",
        f"- Evidence definitions: {len(record.relevant_evidence_ids)}",
        f"- Engineering rules: {len(record.relevant_rule_ids)}",
        "",
        "## Known Limitations",
    ])
    lines.extend(f"- {item}" for item in record.limitations)
    if not record.limitations:
        lines.append("- No additional limitations were recorded.")
    lines.extend([
        "",
        "## Unsupported Boundaries",
        "- Unsupported behavior remains outside the declared model-family scope and must not be inferred as accepted.",
        "",
        "## Artifact and Package Integrity",
    ])
    integrity_findings = [
        finding for finding in record.findings
        if finding.check_id.endswith("artifact_integrity") or finding.check_id.endswith("audit_package")
    ]
    lines.extend(f"- {finding.title}: {finding.status}" for finding in integrity_findings)
    if not integrity_findings:
        lines.append("- Not required by this policy.")
    lines.extend([
        "",
        "## Review Notice",
        record.review_notice,
        "",
        "## Decision Identity",
        f"- Decision ID: {record.decision_id}",
        f"- Content ID: {record.content_id}",
        "",
        "This deterministic policy decision is not regulatory approval, legal certification, a safety guarantee, or production authorization.",
        "",
    ])
    return "\n".join(lines)
