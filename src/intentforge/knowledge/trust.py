"""Engineering evidence trust reporting."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.capability_schema import SUPPORTED_CAPABILITY_FAMILIES, SUPPORTED_CAPABILITY_STAGES
from intentforge.knowledge.evidence_bundles import build_all_evidence_bundles
from intentforge.knowledge.evidence_registry import load_evidence_definitions, load_evidence_manifest, validate_evidence_manifest
from intentforge.knowledge.evidence_resolver import resolve_evidence
from intentforge.knowledge.evidence_schema import (
    EvidenceBundle,
    EvidenceDefinition,
    EvidenceObservation,
    TrustReport,
    fixed_evidence_timestamp,
    stable_evidence_digest,
)


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else 1.0,
    }


def _role_completeness(
    definitions: list[EvidenceDefinition],
    observations_by_id: dict[str, EvidenceObservation],
    role: str,
) -> dict[str, Any]:
    required = [definition for definition in definitions if definition.required and definition.role == role]
    verified = [
        definition
        for definition in required
        if (observation := observations_by_id.get(definition.evidence_id)) is not None
        and observation.status == "verified"
        and observation.matches_expectation
    ]
    return _ratio(len(verified), len(required))


def _summarize_by_family(definitions: list[EvidenceDefinition], observations_by_id: dict[str, EvidenceObservation]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for family in SUPPORTED_CAPABILITY_FAMILIES:
        family_definitions = [definition for definition in definitions if definition.family == family]
        family_observations = [observations_by_id[definition.evidence_id] for definition in family_definitions if definition.evidence_id in observations_by_id]
        counts = Counter(observation.status for observation in family_observations)
        summary[family] = {
            "evidence_count": len(family_definitions),
            "verified": counts.get("verified", 0),
            "failed": counts.get("failed", 0),
            "unresolved": counts.get("unresolved", 0),
            "stale": counts.get("stale", 0),
        }
    return summary


def _summarize_by_stage(definitions: list[EvidenceDefinition], observations_by_id: dict[str, EvidenceObservation]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for stage in SUPPORTED_CAPABILITY_STAGES:
        stage_definitions = [definition for definition in definitions if stage in definition.stages]
        stage_observations = [observations_by_id[definition.evidence_id] for definition in stage_definitions if definition.evidence_id in observations_by_id]
        counts = Counter(observation.status for observation in stage_observations)
        summary[stage] = {
            "evidence_count": len(stage_definitions),
            "verified": counts.get("verified", 0),
            "failed": counts.get("failed", 0),
            "unresolved": counts.get("unresolved", 0),
            "stale": counts.get("stale", 0),
        }
    return summary


def _summarize_by_field(definitions: list[EvidenceDefinition], observations_by_id: dict[str, EvidenceObservation], field_name: str) -> dict[str, dict[str, int]]:
    values = sorted({str(getattr(definition, field_name)) for definition in definitions})
    summary: dict[str, dict[str, int]] = {}
    for value in values:
        selected = [definition for definition in definitions if str(getattr(definition, field_name)) == value]
        selected_observations = [observations_by_id[definition.evidence_id] for definition in selected if definition.evidence_id in observations_by_id]
        counts = Counter(observation.status for observation in selected_observations)
        summary[value] = {
            "evidence_count": len(selected),
            "verified": counts.get("verified", 0),
            "failed": counts.get("failed", 0),
            "unresolved": counts.get("unresolved", 0),
            "stale": counts.get("stale", 0),
        }
    return summary


def _status_counts(observations: list[EvidenceObservation]) -> Counter[str]:
    return Counter(observation.status for observation in observations)


def generate_trust_report(
    definitions: list[EvidenceDefinition] | None = None,
    observations: list[EvidenceObservation] | None = None,
    *,
    runtime: bool = False,
) -> TrustReport:
    """Generate a deterministic evidence trust report."""

    manifest = load_evidence_manifest()
    active_definitions = sorted(definitions or manifest.evidence, key=lambda item: item.evidence_id)
    resolution = resolve_evidence(active_definitions, runtime=runtime) if observations is None else None
    active_observations = sorted(observations or resolution.observations, key=lambda item: item.evidence_id)
    observations_by_id = {observation.evidence_id: observation for observation in active_observations}
    validation = validate_evidence_manifest()
    capability_manifest = load_capability_manifest()
    capabilities = sorted(capability_manifest.capabilities, key=lambda item: item.capability_id)
    bundles = build_all_evidence_bundles(active_definitions, active_observations)
    bundles_by_capability = {bundle.capability_id: bundle for bundle in bundles}
    status_counts = Counter(capability.status for capability in capabilities)
    observation_status_counts = _status_counts(active_observations)

    supported_complete: list[str] = []
    supported_incomplete: list[str] = []
    partial_with_limitations: list[str] = []
    partial_missing_limitations: list[str] = []
    unsupported_with_rejection: list[str] = []
    unsupported_missing_rejection: list[str] = []

    for capability in capabilities:
        bundle = bundles_by_capability[capability.capability_id]
        if capability.status == "supported":
            if bundle.bundle_status == "evidence_complete":
                supported_complete.append(capability.capability_id)
            else:
                supported_incomplete.append(capability.capability_id)
        if capability.status == "partially_supported":
            has_limitation = any(
                observation.status == "verified" and observation.matches_expectation
                for observation in bundle.limitation_evidence
            )
            if has_limitation:
                partial_with_limitations.append(capability.capability_id)
            else:
                partial_missing_limitations.append(capability.capability_id)
        if capability.status == "unsupported":
            has_boundary = any(
                observation.status == "verified" and observation.matches_expectation
                for observation in bundle.boundary_evidence
            )
            if has_boundary:
                unsupported_with_rejection.append(capability.capability_id)
            else:
                unsupported_missing_rejection.append(capability.capability_id)

    required_evidence_count = len([definition for definition in active_definitions if definition.required])
    validation_summary = validation.summary
    implementation = _role_completeness(active_definitions, observations_by_id, "implementation")
    verification = _role_completeness(active_definitions, observations_by_id, "verification")
    boundary = _role_completeness(active_definitions, observations_by_id, "boundary")
    limitation = _role_completeness(active_definitions, observations_by_id, "limitation")
    gate_passed = (
        validation.passed
        and not supported_incomplete
        and not partial_missing_limitations
        and not unsupported_missing_rejection
        and observation_status_counts.get("failed", 0) == 0
        and observation_status_counts.get("unresolved", 0) == 0
        and observation_status_counts.get("unavailable", 0) == 0
        and observation_status_counts.get("stale", 0) == 0
    )
    identity = {
        "manifest_version": manifest.manifest_version,
        "definition_ids": [definition.evidence_id for definition in active_definitions],
        "observation_content_ids": [observation.content_id for observation in active_observations],
        "bundle_ids": [bundle.bundle_id for bundle in bundles],
        "validation_summary": validation_summary,
        "runtime": runtime,
    }
    report_id = stable_evidence_digest("trust_report", identity)
    return TrustReport(
        report_id=report_id,
        generated_at=fixed_evidence_timestamp(),
        manifest_version=manifest.manifest_version,
        declared_capability_count=len(capabilities),
        supported_capability_count=status_counts.get("supported", 0),
        partially_supported_capability_count=status_counts.get("partially_supported", 0),
        unsupported_boundary_count=status_counts.get("unsupported", 0),
        total_evidence_definition_count=len(active_definitions),
        required_evidence_count=required_evidence_count,
        verified_evidence_count=observation_status_counts.get("verified", 0),
        failed_evidence_count=observation_status_counts.get("failed", 0),
        unresolved_evidence_count=observation_status_counts.get("unresolved", 0),
        unavailable_evidence_count=observation_status_counts.get("unavailable", 0),
        stale_evidence_count=observation_status_counts.get("stale", 0),
        orphan_evidence_count=int(validation_summary.get("orphan_evidence_count", 0)),
        duplicate_evidence_id_count=int(validation_summary.get("duplicate_evidence_id_count", 0)),
        duplicate_normalized_reference_count=int(validation_summary.get("duplicate_normalized_reference_count", 0)),
        family_mismatch_count=int(validation_summary.get("family_mismatch_count", 0)),
        stage_mismatch_count=int(validation_summary.get("stage_mismatch_count", 0)),
        capability_mismatch_count=int(validation_summary.get("unknown_capability_reference_count", 0)),
        unknown_rule_reference_count=int(validation_summary.get("unknown_rule_reference_count", 0)),
        unknown_pack_reference_count=int(validation_summary.get("unknown_pack_reference_count", 0)),
        unknown_capability_reference_count=int(validation_summary.get("unknown_capability_reference_count", 0)),
        supported_capabilities_with_complete_evidence=supported_complete,
        supported_capabilities_with_incomplete_evidence=supported_incomplete,
        partially_supported_capabilities_with_complete_limitation_evidence=partial_with_limitations,
        partially_supported_capabilities_missing_limitation_evidence=partial_missing_limitations,
        unsupported_boundaries_with_verified_rejection_evidence=unsupported_with_rejection,
        unsupported_boundaries_missing_rejection_evidence=unsupported_missing_rejection,
        implementation_evidence_completeness=implementation,
        verification_evidence_completeness=verification,
        boundary_evidence_completeness=boundary,
        limitation_evidence_completeness=limitation,
        per_family=_summarize_by_family(active_definitions, observations_by_id),
        per_stage=_summarize_by_stage(active_definitions, observations_by_id),
        per_evidence_type=_summarize_by_field(active_definitions, observations_by_id, "evidence_type"),
        per_evidence_role=_summarize_by_field(active_definitions, observations_by_id, "role"),
        bundles=bundles,
        observations=active_observations,
        validation_errors=validation.errors,
        validation_warnings=validation.warnings,
        overall_trust_gate_passed=gate_passed,
        summary={
            "runtime_verification": runtime,
            "implementation_evidence_completeness": implementation,
            "verification_evidence_completeness": verification,
            "boundary_evidence_completeness": boundary,
            "limitation_evidence_completeness": limitation,
            "evidence_complete_for_declared_scope": gate_passed,
        },
    )


def filter_evidence_bundles(
    bundles: Iterable[EvidenceBundle],
    *,
    family: str | None = None,
    capability_id: str | None = None,
) -> list[EvidenceBundle]:
    """Filter trust report evidence bundles."""

    selected = list(bundles)
    if family:
        selected = [bundle for bundle in selected if bundle.family == family]
    if capability_id:
        selected = [bundle for bundle in selected if bundle.capability_id == capability_id]
    return sorted(selected, key=lambda item: item.capability_id)
