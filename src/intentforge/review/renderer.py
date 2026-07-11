"""Deterministic Markdown rendering for engineering review decisions."""

from __future__ import annotations

from intentforge.review.diff_schema import MultiVariantReviewDiff, ReviewDecisionDiff
from intentforge.review.provenance import verify_decision_provenance
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
    ])
    if record.decision_provenance is not None:
        provenance = record.decision_provenance
        lines.extend([
            "",
            "## Decision Provenance",
            f"- Provenance ID: {provenance.provenance_id}",
            f"- Evaluator version: {provenance.evaluator_version}",
            f"- Check registry version: {provenance.check_registry_version}",
            f"- Decision strategy: {provenance.decision_strategy}",
            f"- Frozen snapshots: {len(provenance.snapshots)}",
            f"- Execution nodes: {len(provenance.execution_nodes)}",
            f"- Evidence matrix: {provenance.evidence_definition_count} definitions, {provenance.evidence_observation_count} observations",
        ])
    lines.extend([
        "",
        "This deterministic policy decision is not regulatory approval, legal certification, a safety guarantee, or production authorization.",
        "",
    ])
    return "\n".join(lines)


def render_decision_provenance_markdown(
    decision: ReviewDecision | dict,
    *,
    verify: bool = False,
) -> str:
    """Render frozen execution provenance without exposing executable internals."""

    record = decision if isinstance(decision, ReviewDecision) else ReviewDecision.model_validate(decision)
    provenance = record.decision_provenance
    if provenance is None:
        return (
            "# IntentForge Review Decision Provenance\n\n"
            f"- Decision ID: {record.decision_id}\n"
            "- Status: provenance_missing\n\n"
            "This legacy decision does not contain a frozen Phase 25 provenance record.\n"
        )
    validation = verify_decision_provenance(record, perform_replay=verify)
    lines = [
        "# IntentForge Review Decision Provenance",
        "",
        "## Identity",
        f"- Decision ID: {record.decision_id}",
        f"- Provenance ID: {provenance.provenance_id}",
        f"- Provenance content ID: {provenance.content_id}",
        f"- Schema version: {provenance.schema_version}",
        f"- Tool version: {provenance.tool_version}",
        f"- Evaluator version: {provenance.evaluator_version}",
        f"- Check registry version: {provenance.check_registry_version}",
        f"- Check registry content ID: {provenance.check_registry_content_id}",
        f"- Decision strategy: {provenance.decision_strategy}",
        "",
        "## Frozen Inputs",
    ]
    lines.extend(
        f"- {item.snapshot_type}: {item.reference_id} v{item.version} ({item.content_id})"
        for item in provenance.snapshots
    )
    lines.extend([
        "",
        "## Evidence Matrix",
        f"- Definitions frozen: {provenance.evidence_definition_count}",
        f"- Observations frozen: {provenance.evidence_observation_count}",
        "- Runtime verification: not implied by static provenance unless separately recorded.",
        "",
        "## Execution Chain",
    ])
    lines.extend(
        f"- {item.sequence}. {item.node_key}: {item.status} ({item.content_id})"
        for item in provenance.execution_nodes
    )
    lines.extend([
        "",
        "## Trace Verification",
        f"- Status: {validation.status}",
        f"- Snapshot mismatches: {validation.snapshot_mismatch_count}",
        f"- Execution node mismatches: {validation.execution_node_mismatch_count}",
        f"- Replay requested: {str(verify).lower()}",
        f"- Replay performed: {str(validation.replay_performed).lower()}",
        f"- Replay mismatches: {validation.replay_mismatch_count}",
    ])
    if validation.errors:
        lines.extend(["", "## Errors", *(f"- {item}" for item in validation.errors)])
    if validation.warnings:
        lines.extend(["", "## Warnings", *(f"- {item}" for item in validation.warnings)])
    lines.extend([
        "",
        "The provenance record verifies deterministic review execution within the recorded IntentForge contract. It is not engineering certification.",
        "",
    ])
    return "\n".join(lines)


_TRANSITION_LANGUAGE = {
    "unchanged": "The final acceptance outcome is unchanged.",
    "acceptance_elevated": "The candidate has a more permissive acceptance outcome than the baseline.",
    "acceptance_constrained": "The candidate has a more restrictive acceptance outcome than the baseline.",
    "status_changed": "The final outcome changed without a safe acceptance-order interpretation.",
}


def render_review_diff_markdown(diff: ReviewDecisionDiff | dict) -> str:
    """Render a deterministic semantic delta report from structured changes."""

    record = diff if isinstance(diff, ReviewDecisionDiff) else ReviewDecisionDiff.model_validate(diff)
    lines = [
        "# IntentForge Review Decision Differential Audit",
        "",
        "## Comparison Identity",
        f"- Diff ID: {record.diff_id}",
        f"- Baseline decision: {record.baseline_decision_id}",
        f"- Candidate decision: {record.candidate_decision_id}",
        f"- Identical: {str(record.identical).lower()}",
        "",
        "## Acceptance Outcome",
        f"- Baseline: {record.baseline_status}",
        f"- Candidate: {record.candidate_status}",
        f"- Transition: {record.decision_transition}",
        f"- Interpretation: {_TRANSITION_LANGUAGE[record.decision_transition]}",
        "",
        "## Structural Summary",
        f"- Policy configuration changed: {str(record.policy_changed).lower()}",
        f"- Evaluation graph changed: {str(record.evaluation_graph_changed).lower()}",
        f"- Semantic deltas: {len(record.deltas)}",
        f"- Security/compliance-relevant deltas: {len(record.security_compliance_delta_ids)}",
        f"- Added checks: {', '.join(record.added_check_ids) if record.added_check_ids else 'none'}",
        f"- Removed checks: {', '.join(record.removed_check_ids) if record.removed_check_ids else 'none'}",
        f"- Modified checks: {', '.join(record.modified_check_ids) if record.modified_check_ids else 'none'}",
    ]
    for title, category in (
        ("Policy Configuration Deltas", "policy"),
        ("Evaluation Graph Deltas", "evaluation_graph"),
        ("Finding Deltas", "finding"),
        ("Condition Deltas", "condition"),
        ("Outcome Deltas", "outcome"),
        ("Reference and Provenance Deltas", None),
    ):
        selected = [
            item for item in record.deltas
            if item.category == category
            or category is None and item.category in {
                "subject", "capability", "evidence", "rule", "limitation", "provenance"
            }
        ]
        lines.extend(["", f"## {title}"])
        if not selected:
            lines.append("- None.")
        else:
            lines.extend(
                f"- {item.category}/{item.entity_key}: {item.change_type}; fields={', '.join(item.changed_fields) or 'value'}; impact={item.compliance_impact}; code={item.summary_code}"
                for item in selected
            )
    lines.extend([
        "",
        "## Interpretation Boundary",
        "This report compares deterministic policy structures and recorded outcomes. It does not perform geometric visual diffing, simulation, or engineering certification.",
        "",
    ])
    return "\n".join(lines)


def render_multi_variant_diff_markdown(diff: MultiVariantReviewDiff | dict) -> str:
    """Render one baseline and all pairwise deterministic variant deltas."""

    record = diff if isinstance(diff, MultiVariantReviewDiff) else MultiVariantReviewDiff.model_validate(diff)
    lines = [
        "# IntentForge Multi-Variant Review Differential Audit",
        "",
        "## Audit Summary",
        f"- Audit ID: {record.audit_id}",
        f"- Baseline decision: {record.baseline_decision_id}",
        f"- Variants: {len(record.variant_decision_ids)}",
        f"- Identical variants: {record.identical_variant_count}",
        f"- Acceptance elevations: {record.elevated_variant_count}",
        f"- Acceptance constraints: {record.constrained_variant_count}",
        f"- Other status changes: {record.changed_variant_count}",
        f"- Security/compliance-relevant deltas: {record.security_compliance_change_count}",
        "",
        "## Outcome Matrix",
    ]
    lines.extend(f"- {key}: {record.outcome_matrix[key]}" for key in sorted(record.outcome_matrix))
    for index, item in enumerate(record.pairwise_diffs, start=1):
        lines.extend([
            "",
            f"## Variant {index}: {item.candidate_decision_id}",
            f"- Diff ID: {item.diff_id}",
            f"- Transition: {item.decision_transition}",
            f"- Semantic deltas: {len(item.deltas)}",
            f"- Security/compliance-relevant deltas: {len(item.security_compliance_delta_ids)}",
            f"- Policy changed: {str(item.policy_changed).lower()}",
            f"- Evaluation graph changed: {str(item.evaluation_graph_changed).lower()}",
        ])
    lines.extend([
        "",
        "The baseline remains fixed for every pairwise comparison. This report does not infer unrecorded engineering behavior or certification.",
        "",
    ])
    return "\n".join(lines)
