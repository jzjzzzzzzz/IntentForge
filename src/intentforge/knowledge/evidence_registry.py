"""Loading, filtering, and validation helpers for evidence definitions."""

from __future__ import annotations

from collections import Counter
from importlib import resources
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import ValidationError

from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.capability_schema import SUPPORTED_CAPABILITY_FAMILIES
from intentforge.knowledge.evidence_schema import (
    EvidenceDefinition,
    EvidenceManifest,
    EvidenceRole,
    EvidenceType,
    EvidenceValidationResult,
)
from intentforge.knowledge.packs.registry import RulePackRegistry
from intentforge.knowledge.rules import RuleRegistry


DEFAULT_EVIDENCE_MANIFEST_RESOURCE = "evidence_manifest.yaml"


class EvidenceManifestError(ValueError):
    """Raised when evidence manifest loading fails."""


def _read_manifest_yaml(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        text = resources.files("intentforge.knowledge.data").joinpath(
            DEFAULT_EVIDENCE_MANIFEST_RESOURCE
        ).read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    if not isinstance(raw, dict):
        raise EvidenceManifestError("evidence manifest must contain a YAML mapping")
    return raw


def load_evidence_manifest(path: str | Path | None = None) -> EvidenceManifest:
    """Load the packaged or user-provided evidence manifest."""

    try:
        return EvidenceManifest.model_validate(_read_manifest_yaml(path))
    except ValidationError as exc:
        raise EvidenceManifestError(str(exc)) from exc


def load_evidence_definitions(path: str | Path | None = None) -> list[EvidenceDefinition]:
    """Load evidence definitions in deterministic manifest order."""

    return load_evidence_manifest(path).evidence


class EvidenceRegistry:
    """Deterministic registry for evidence definitions."""

    def __init__(self, definitions: Iterable[EvidenceDefinition]):
        self._definitions = sorted(list(definitions), key=lambda item: item.evidence_id)
        evidence_ids = [definition.evidence_id for definition in self._definitions]
        duplicates = sorted(item for item, count in Counter(evidence_ids).items() if count > 1)
        if duplicates:
            raise EvidenceManifestError(f"duplicate evidence ids: {', '.join(duplicates)}")

    @classmethod
    def load_default(cls) -> "EvidenceRegistry":
        return cls(load_evidence_definitions())

    def all(self) -> list[EvidenceDefinition]:
        return list(self._definitions)

    def count(self) -> int:
        return len(self._definitions)

    def get(self, evidence_id: str) -> EvidenceDefinition | None:
        for definition in self._definitions:
            if definition.evidence_id == evidence_id:
                return definition
        return None

    def filter(
        self,
        *,
        family: str | None = None,
        evidence_type: str | None = None,
        role: str | None = None,
        capability_id: str | None = None,
    ) -> list[EvidenceDefinition]:
        definitions = self._definitions
        if family:
            definitions = [
                definition
                for definition in definitions
                if definition.family == family or family in definition.provenance.get("families", [])
            ]
        if evidence_type:
            definitions = [definition for definition in definitions if definition.evidence_type == evidence_type]
        if role:
            definitions = [definition for definition in definitions if definition.role == role]
        if capability_id:
            definitions = [definition for definition in definitions if capability_id in definition.capability_ids]
        return list(definitions)

    def by_capability(self) -> dict[str, list[EvidenceDefinition]]:
        result: dict[str, list[EvidenceDefinition]] = {}
        for definition in self._definitions:
            for capability_id in definition.capability_ids:
                result.setdefault(capability_id, []).append(definition)
        return {key: sorted(value, key=lambda item: item.evidence_id) for key, value in sorted(result.items())}

    def normalized_reference_counts(self) -> dict[tuple[str, str, str], int]:
        counter: Counter[tuple[str, str, str]] = Counter()
        for definition in self._definitions:
            counter[(definition.evidence_type, definition.role, definition.normalized_reference)] += 1
        return dict(counter)


def _error(errors: list[dict[str, Any]], message: str, **context: Any) -> None:
    errors.append({"message": message, **{key: value for key, value in context.items() if value is not None}})


def _raw_duplicate_ids(raw: dict[str, Any]) -> list[str]:
    evidence = raw.get("evidence", [])
    if not isinstance(evidence, list):
        return []
    ids = [item.get("evidence_id") for item in evidence if isinstance(item, dict)]
    return sorted(str(item) for item, count in Counter(ids).items() if item and count > 1)


def validate_evidence_manifest(
    manifest: EvidenceManifest | None = None,
    *,
    path: str | Path | None = None,
    rule_registry: RuleRegistry | None = None,
    pack_registry: RulePackRegistry | None = None,
) -> EvidenceValidationResult:
    """Validate evidence definitions against capabilities, rules, packs, and families."""

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    raw_duplicate_ids: list[str] = []
    active_manifest: EvidenceManifest | None = manifest
    if active_manifest is None:
        try:
            raw = _read_manifest_yaml(path)
            raw_duplicate_ids = _raw_duplicate_ids(raw)
            active_manifest = EvidenceManifest.model_validate(raw)
        except (EvidenceManifestError, ValidationError) as exc:
            for duplicate_id in raw_duplicate_ids:
                _error(errors, "duplicate evidence id", evidence_id=duplicate_id)
            _error(errors, str(exc), field="manifest")
            return EvidenceValidationResult(
                passed=False,
                evidence_checked=0,
                errors=errors,
                warnings=warnings,
                summary={
                    "duplicate_evidence_id_count": len(raw_duplicate_ids),
                    "unknown_capability_reference_count": 0,
                    "unknown_rule_reference_count": 0,
                    "unknown_pack_reference_count": 0,
                },
            )

    active_rule_registry = rule_registry or RuleRegistry.load()
    active_pack_registry = pack_registry or RulePackRegistry.load_default()
    capability_manifest = load_capability_manifest()
    capability_ids = {capability.capability_id for capability in capability_manifest.capabilities}
    capabilities_by_id = {capability.capability_id: capability for capability in capability_manifest.capabilities}
    rule_ids = {rule.id for rule in active_rule_registry.get_active_rules()}
    pack_ids = {pack.pack_id for pack in active_pack_registry.all_packs()}
    evidence_ids = [definition.evidence_id for definition in active_manifest.evidence]
    duplicate_ids = sorted(item for item, count in Counter(evidence_ids).items() if count > 1)

    unknown_capabilities: set[str] = set()
    unknown_rules: set[str] = set()
    unknown_packs: set[str] = set()
    family_mismatches: list[dict[str, Any]] = []
    stage_mismatches: list[dict[str, Any]] = []
    duplicate_references: list[dict[str, Any]] = []
    orphan_evidence: list[str] = []
    supported_missing_impl: list[str] = []
    supported_missing_verification: list[str] = []
    partial_missing_limitation: list[str] = []
    unsupported_missing_boundary: list[str] = []
    unsafe_file_refs: list[str] = []

    for duplicate_id in duplicate_ids:
        _error(errors, "duplicate evidence id", evidence_id=duplicate_id)

    reference_groups: dict[tuple[str, str, str], list[EvidenceDefinition]] = {}
    for definition in active_manifest.evidence:
        reference_groups.setdefault(
            (definition.evidence_type, definition.role, definition.normalized_reference),
            [],
        ).append(definition)
    for definition in active_manifest.evidence:
        ref_key = (definition.evidence_type, definition.role, definition.normalized_reference)
        duplicate_group = reference_groups[ref_key]
        if len(duplicate_group) > 1 and not any(item.reuse_reason for item in duplicate_group):
            duplicate_references.append(
                {
                    "evidence_id": definition.evidence_id,
                    "evidence_type": definition.evidence_type,
                    "role": definition.role,
                    "reference": definition.reference,
                }
            )
            _error(errors, "duplicate normalized evidence reference without reuse reason", evidence_id=definition.evidence_id)

        if definition.reference.startswith(("http://", "https://")) or "%2e" in definition.reference.lower():
            unsafe_file_refs.append(definition.evidence_id)
            _error(errors, "unsafe evidence reference", evidence_id=definition.evidence_id, reference=definition.reference)

        for capability_id in definition.capability_ids:
            if capability_id not in capability_ids:
                unknown_capabilities.add(capability_id)
                _error(errors, "unknown capability reference", evidence_id=definition.evidence_id, capability_id=capability_id)
                continue
            capability = capabilities_by_id[capability_id]
            if definition.family and definition.family != capability.family:
                family_mismatches.append({"evidence_id": definition.evidence_id, "capability_id": capability_id})
                _error(errors, "evidence family does not match capability family", evidence_id=definition.evidence_id, capability_id=capability_id)
            if definition.stages and not (set(definition.stages) & set(capability.stages)):
                stage_mismatches.append({"evidence_id": definition.evidence_id, "capability_id": capability_id})
                _error(errors, "evidence stage does not overlap capability stages", evidence_id=definition.evidence_id, capability_id=capability_id)

        for rule_id in definition.rule_ids:
            if rule_id not in rule_ids:
                unknown_rules.add(rule_id)
                _error(errors, "unknown rule reference", evidence_id=definition.evidence_id, rule_id=rule_id)
        for pack_id in definition.pack_ids:
            if pack_id not in pack_ids:
                unknown_packs.add(pack_id)
                _error(errors, "unknown pack reference", evidence_id=definition.evidence_id, pack_id=pack_id)

        if not definition.capability_ids and not definition.rule_ids and not definition.pack_ids:
            if definition.role not in {"provenance", "packaging"} and not definition.provenance.get("purpose"):
                orphan_evidence.append(definition.evidence_id)
                _error(errors, "evidence is not attached to a capability, rule, pack, or provenance purpose", evidence_id=definition.evidence_id)

    definitions_by_capability: dict[str, list[EvidenceDefinition]] = {}
    for definition in active_manifest.evidence:
        for capability_id in definition.capability_ids:
            definitions_by_capability.setdefault(capability_id, []).append(definition)

    for capability in capability_manifest.capabilities:
        definitions = definitions_by_capability.get(capability.capability_id, [])
        required_definitions = [definition for definition in definitions if definition.required]
        roles = {definition.role for definition in required_definitions}
        if capability.status == "supported":
            if "implementation" not in roles:
                supported_missing_impl.append(capability.capability_id)
                _error(errors, "supported capability missing required implementation evidence", capability_id=capability.capability_id)
            if "verification" not in roles:
                supported_missing_verification.append(capability.capability_id)
                _error(errors, "supported capability missing required verification evidence", capability_id=capability.capability_id)
            verification_definitions = [definition for definition in required_definitions if definition.role == "verification"]
            if verification_definitions and all(definition.evidence_type == "documentation" for definition in verification_definitions):
                _error(errors, "documentation is the sole verification evidence for supported capability", capability_id=capability.capability_id)
        if capability.status == "partially_supported" and "limitation" not in roles:
            partial_missing_limitation.append(capability.capability_id)
            _error(errors, "partially supported capability missing required limitation evidence", capability_id=capability.capability_id)
        if capability.status == "unsupported" and "boundary" not in roles:
            unsupported_missing_boundary.append(capability.capability_id)
            _error(errors, "unsupported boundary missing required rejection evidence", capability_id=capability.capability_id)

    summary = {
        "evidence_definition_count": len(active_manifest.evidence),
        "duplicate_evidence_id_count": len(duplicate_ids),
        "duplicate_normalized_reference_count": len(duplicate_references),
        "unknown_capability_reference_count": len(unknown_capabilities),
        "unknown_rule_reference_count": len(unknown_rules),
        "unknown_pack_reference_count": len(unknown_packs),
        "family_mismatch_count": len(family_mismatches),
        "stage_mismatch_count": len(stage_mismatches),
        "orphan_evidence_count": len(orphan_evidence),
        "unsafe_file_reference_count": len(unsafe_file_refs),
        "supported_missing_implementation_count": len(supported_missing_impl),
        "supported_missing_verification_count": len(supported_missing_verification),
        "partial_missing_limitation_count": len(partial_missing_limitation),
        "unsupported_missing_boundary_count": len(unsupported_missing_boundary),
        "supported_capabilities_missing_required_implementation_evidence": supported_missing_impl,
        "supported_capabilities_missing_required_verification_evidence": supported_missing_verification,
        "partially_supported_capabilities_missing_limitation_evidence": partial_missing_limitation,
        "unsupported_boundaries_missing_rejection_evidence": unsupported_missing_boundary,
        "orphan_evidence": orphan_evidence,
        "duplicate_normalized_references": duplicate_references,
        "unknown_capability_references": sorted(unknown_capabilities),
        "unknown_rule_references": sorted(unknown_rules),
        "unknown_pack_references": sorted(unknown_packs),
        "family_mismatches": family_mismatches,
        "stage_mismatches": stage_mismatches,
    }
    return EvidenceValidationResult(
        passed=not errors,
        evidence_checked=len(active_manifest.evidence),
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def filter_evidence(
    definitions: Iterable[EvidenceDefinition],
    *,
    family: str | None = None,
    evidence_type: EvidenceType | str | None = None,
    role: EvidenceRole | str | None = None,
    capability_id: str | None = None,
) -> list[EvidenceDefinition]:
    """Filter evidence definitions without mutating ordering."""

    registry = EvidenceRegistry(definitions)
    return registry.filter(family=family, evidence_type=evidence_type, role=role, capability_id=capability_id)


def validate_family_filter(family: str | None) -> str | None:
    if family is not None and family not in SUPPORTED_CAPABILITY_FAMILIES:
        raise EvidenceManifestError(f"unsupported evidence family: {family}")
    return family
