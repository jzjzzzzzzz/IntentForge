"""Deterministic human-readable rendering for assurance cases."""

from __future__ import annotations

from intentforge.assurance.schema import AssuranceCase


def render_assurance_markdown(case: AssuranceCase | dict) -> str:
    record = case if isinstance(case, AssuranceCase) else AssuranceCase.model_validate(case)
    lines = [
        "# IntentForge Engineering Assurance Case", "", "## Design Request",
        str(record.input_request.get("summary") or "Not recorded."), "", "## Interpreted Design Intent",
        f"- Structured intent recorded: {str(record.structured_intent is not None).lower()}", "",
        "## Operation and CAD Family", f"- Operation: {record.operation}", f"- CAD family: {record.cad_family}",
        f"- Assurance profile: {record.profile}", "", "## Feature Plan",
        f"- Planned steps: {len(record.feature_plan_summary.get('steps', []))}", "", "## Engineering Rules Applied",
    ]
    for rule in record.rule_references:
        lines.append(f"- {rule['rule_id']} v{rule.get('rule_version')}: {rule.get('outcome')} ({rule.get('pack_id')})")
    lines.extend(["", "## Constraints and Decisions", f"- Compiled constraints recorded: {len(record.compiled_constraint_summary)}",
                  "", "## Geometry Validation"])
    for observation in record.validation_observations:
        lines.append(f"- {observation.validation_type}: {observation.status}")
    if not record.validation_observations: lines.append("- Not executed for this assurance profile.")
    lines.extend(["", "## Topology and Feature Recognition"])
    for kind in ("topology_inspection", "feature_recognition"):
        found = [item for item in record.validation_observations if item.validation_type == kind]
        lines.append(f"- {kind}: {found[0].status if found else 'not checked'}")
    lines.extend(["", "## Engineering Reasoning", f"- Report included: {str(record.reasoning_summary is not None).lower()}",
                  "", "## Capability Claims Exercised"])
    for capability_id in record.capability_references: lines.append(f"- {capability_id}")
    lines.extend(["", "## Evidence Summary", f"- Evidence references: {len(record.evidence_references)}", "",
                  "## Assurance Claims"])
    for claim in record.claims:
        lines.append(f"- {claim.status.upper()}: {claim.title}. {claim.statement}")
    lines.extend(["", "## Known Limitations"])
    for limitation in record.limitations: lines.append(f"- {limitation.title}: {limitation.description}")
    if not record.limitations: lines.append("- No additional declared limitations were mapped to this run.")
    lines.extend(["", "## Unsupported Boundaries"])
    boundaries = [item for item in record.limitations if item.significance == "unsupported_boundary"]
    for item in boundaries: lines.append(f"- {item.description}")
    if not boundaries: lines.append("- No unsupported boundary was exercised by this request.")
    lines.extend(["", "## Artifact Integrity", f"- Artifact records: {len(record.artifact_records)}",
                  f"- Hashed artifacts: {sum(1 for item in record.artifact_records if item.content_hash)}", "",
                  "## Reproducibility", f"- Deterministic case ID: {record.assurance_case_id}",
                  f"- Deterministic content ID: {record.content_id}", "", "## Review Requirements"])
    lines.extend(f"- {item}" for item in record.review_requirements)
    lines.extend(["", "## Overall Assurance Status", f"**{record.overall_assurance_status}**", "",
                  "This record provides assurance within the declared IntentForge scope. It does not certify safety, manufacturability, regulatory approval, or fitness for a specific external use.", ""])
    return "\n".join(lines)
