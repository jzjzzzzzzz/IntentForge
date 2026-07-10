"""Capability evidence bundle assembly."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.capability_schema import CapabilityDefinition
from intentforge.knowledge.evidence_registry import EvidenceRegistry, load_evidence_definitions
from intentforge.knowledge.evidence_resolver import resolve_evidence
from intentforge.knowledge.evidence_schema import (
    EvidenceBundle,
    EvidenceBundleStatus,
    EvidenceDefinition,
    EvidenceObservation,
    make_bundle_id,
)


def _status_complete(observation: EvidenceObservation) -> bool:
    return observation.status == "verified" and observation.matches_expectation


def _role_observations(
    observations: list[EvidenceObservation],
    definitions_by_id: dict[str, EvidenceDefinition],
    role: str,
) -> list[EvidenceObservation]:
    selected = [
        observation
        for observation in observations
        if definitions_by_id[observation.evidence_id].role == role
    ]
    return sorted(selected, key=lambda item: item.evidence_id)


def _bundle_status(capability: CapabilityDefinition, observations: list[EvidenceObservation]) -> EvidenceBundleStatus:
    if capability.status == "not_applicable":
        return "not_applicable"
    if any(observation.status == "failed" for observation in observations):
        return "evidence_failed"
    if any(observation.status in {"unresolved", "unavailable"} for observation in observations):
        return "evidence_unresolved"
    if capability.status == "unsupported":
        boundary = [observation for observation in observations if _status_complete(observation)]
        return "boundary_verified" if boundary else "evidence_unresolved"
    required = observations
    if required and all(_status_complete(observation) for observation in required):
        return "evidence_complete"
    return "evidence_partial"


def build_evidence_bundle(
    capability: CapabilityDefinition,
    definitions: Iterable[EvidenceDefinition],
    observations: Iterable[EvidenceObservation],
) -> EvidenceBundle:
    """Build one deterministic evidence bundle for one capability."""

    definitions_for_capability = sorted(
        [definition for definition in definitions if capability.capability_id in definition.capability_ids],
        key=lambda item: item.evidence_id,
    )
    definitions_by_id = {definition.evidence_id: definition for definition in definitions_for_capability}
    observations_by_id = {observation.evidence_id: observation for observation in observations}
    bundle_observations = [
        observations_by_id[definition.evidence_id]
        for definition in definitions_for_capability
        if definition.evidence_id in observations_by_id
    ]
    required_evidence_ids = sorted(definition.evidence_id for definition in definitions_for_capability if definition.required)
    resolved_evidence_ids = sorted(
        observation.evidence_id
        for observation in bundle_observations
        if observation.status in {"verified", "not_applicable"} and observation.matches_expectation
    )
    unresolved_evidence_ids = sorted(
        observation.evidence_id for observation in bundle_observations if observation.status in {"unresolved", "unavailable", "not_checked"}
    )
    failed_evidence_ids = sorted(
        observation.evidence_id for observation in bundle_observations if observation.status == "failed" or not observation.matches_expectation
    )
    stale_evidence_ids = sorted(observation.evidence_id for observation in bundle_observations if observation.status == "stale")
    required_resolved = [evidence_id for evidence_id in required_evidence_ids if evidence_id in resolved_evidence_ids]
    evidence_completeness = len(required_resolved) / len(required_evidence_ids) if required_evidence_ids else 1.0
    status = _bundle_status(capability, [observations_by_id[evidence_id] for evidence_id in required_evidence_ids if evidence_id in observations_by_id])
    diagnostics: list[str] = []
    if unresolved_evidence_ids:
        diagnostics.append(f"unresolved evidence: {', '.join(unresolved_evidence_ids)}")
    if failed_evidence_ids:
        diagnostics.append(f"failed evidence: {', '.join(failed_evidence_ids)}")
    if stale_evidence_ids:
        diagnostics.append(f"stale evidence: {', '.join(stale_evidence_ids)}")

    identity = {
        "capability_id": capability.capability_id,
        "capability_status": capability.status,
        "required_evidence_ids": required_evidence_ids,
        "resolved_evidence_ids": resolved_evidence_ids,
        "unresolved_evidence_ids": unresolved_evidence_ids,
        "failed_evidence_ids": failed_evidence_ids,
        "stale_evidence_ids": stale_evidence_ids,
        "status": status,
    }
    return EvidenceBundle(
        bundle_id=make_bundle_id(identity),
        capability_id=capability.capability_id,
        family=capability.family,
        capability_status=capability.status,
        implementation_evidence=_role_observations(bundle_observations, definitions_by_id, "implementation"),
        verification_evidence=_role_observations(bundle_observations, definitions_by_id, "verification"),
        boundary_evidence=_role_observations(bundle_observations, definitions_by_id, "boundary"),
        limitation_evidence=_role_observations(bundle_observations, definitions_by_id, "limitation"),
        provenance_evidence=_role_observations(bundle_observations, definitions_by_id, "provenance"),
        packaging_evidence=_role_observations(bundle_observations, definitions_by_id, "packaging"),
        required_evidence_ids=required_evidence_ids,
        resolved_evidence_ids=resolved_evidence_ids,
        unresolved_evidence_ids=unresolved_evidence_ids,
        failed_evidence_ids=failed_evidence_ids,
        stale_evidence_ids=stale_evidence_ids,
        evidence_completeness=evidence_completeness,
        bundle_status=status,
        diagnostics=diagnostics,
    )


def build_all_evidence_bundles(
    definitions: list[EvidenceDefinition] | None = None,
    observations: list[EvidenceObservation] | None = None,
    *,
    family: str | None = None,
    capability_id: str | None = None,
    runtime: bool = False,
) -> list[EvidenceBundle]:
    """Build deterministic evidence bundles for all matching capabilities."""

    active_definitions = sorted(definitions or load_evidence_definitions(), key=lambda item: item.evidence_id)
    active_observations = observations or resolve_evidence(active_definitions, runtime=runtime).observations
    capabilities = sorted(load_capability_manifest().capabilities, key=lambda item: item.capability_id)
    if family:
        capabilities = [capability for capability in capabilities if capability.family == family]
    if capability_id:
        capabilities = [capability for capability in capabilities if capability.capability_id == capability_id]
    return [
        build_evidence_bundle(capability, active_definitions, active_observations)
        for capability in capabilities
    ]


def filter_evidence_bundles(
    bundles: Iterable[EvidenceBundle],
    *,
    family: str | None = None,
    capability_id: str | None = None,
) -> list[EvidenceBundle]:
    """Filter evidence bundles by stable public fields."""

    result = list(bundles)
    if family:
        result = [bundle for bundle in result if bundle.family == family]
    if capability_id:
        result = [bundle for bundle in result if bundle.capability_id == capability_id]
    return sorted(result, key=lambda item: item.capability_id)
