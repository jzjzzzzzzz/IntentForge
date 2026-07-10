"""Coverage and capability matrix evaluation for engineering knowledge claims."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import PurePosixPath
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from benchmark.run_benchmark import load_benchmark_cases
from intentforge.knowledge.capabilities import CapabilityManifestError, load_capability_manifest
from intentforge.knowledge.capability_schema import (
    CapabilityDefinition,
    CapabilityManifest,
    CapabilityMatrix,
    CapabilityMatrixRow,
    CapabilityStage,
    CoverageReport,
    EvidenceReference,
    SUPPORTED_CAPABILITY_FAMILIES,
    SUPPORTED_CAPABILITY_STAGES,
    fixed_coverage_timestamp,
    stable_capability_digest,
)
from intentforge.knowledge.packs.registry import RulePackRegistry
from intentforge.knowledge.reasoning.verification import load_golden_cases
from intentforge.knowledge.rules import RuleRegistry


STATIC_EVIDENCE_REFERENCES: dict[str, set[str]] = {
    "parser": {
        "intentforge.parser.requirement_parser",
        "intentforge.parser.edit_parser",
    },
    "schema": {
        "intentforge.schemas.ParameterTable",
        "intentforge.knowledge.schema.DesignKnowledgeRule",
        "intentforge.knowledge.capability_schema.CapabilityDefinition",
        "intentforge.knowledge.packs.schema.RulePack",
        "intentforge.knowledge.reasoning.EngineeringReasoningReport",
    },
    "generator": {
        "intentforge.generator.cadquery_generator.build_wall_bracket",
        "intentforge.generator.cadquery_generator.build_l_bracket",
    },
    "validator": {
        "intentforge.validator.geometry_validator",
        "intentforge.validator.intent_validator",
        "intentforge.knowledge.evaluator.evaluate_parameter_table",
        "intentforge.knowledge.reasoning.build_engineering_reasoning_report",
    },
    "topology_metric": {
        "harness.topology.shape_inspector",
        "harness.topology.volume_delta",
    },
    "feature_recognizer": {
        "harness.topology.feature_recognizer.recognize_wall_bracket_features",
        "harness.topology.feature_recognizer.recognize_l_bracket_features",
        "harness.topology.feature_recognizer.recognize_through_holes",
        "harness.topology.feature_recognizer.recognize_center_cutout",
        "harness.topology.feature_recognizer.recognize_l_bracket_gusset",
        "harness.topology.feature_recognizer.recognize_solid_connectivity",
    },
}


class CapabilityValidationResult(BaseModel):
    """Structured validation result for the capability manifest."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    capabilities_checked: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceCatalog:
    rule_ids: set[str]
    pack_ids: set[str]
    benchmark_case_ids: set[str]
    rejection_case_ids: set[str]
    golden_case_ids: set[str]


def _add_error(errors: list[dict[str, Any]], message: str, **context: Any) -> None:
    errors.append({"message": message, **{key: value for key, value in context.items() if value is not None}})


def _safe_reference(reference: str) -> bool:
    if reference.startswith("/") or "\\" in reference:
        return False
    parts = PurePosixPath(reference).parts
    return ".." not in parts


def build_evidence_catalog(
    *,
    rule_registry: RuleRegistry | None = None,
    pack_registry: RulePackRegistry | None = None,
) -> EvidenceCatalog:
    """Build deterministic evidence identifiers from packaged registries."""

    active_rule_registry = rule_registry or RuleRegistry.load()
    active_pack_registry = pack_registry or RulePackRegistry.load_default()
    benchmark_cases = load_benchmark_cases()
    benchmark_ids = {str(case["id"]) for case in benchmark_cases}
    rejection_ids = {
        str(case["id"])
        for case in benchmark_cases
        if case.get("expected_ok") is False or case.get("category") in {"rejections", "l_rejections"}
    }
    golden_ids = {str(case["id"]) for case in load_golden_cases()}
    return EvidenceCatalog(
        rule_ids={rule.id for rule in active_rule_registry.get_active_rules()},
        pack_ids={pack.pack_id for pack in active_pack_registry.get_active_packs()},
        benchmark_case_ids=benchmark_ids,
        rejection_case_ids=rejection_ids,
        golden_case_ids=golden_ids,
    )


def _evidence_known(evidence: EvidenceReference, catalog: EvidenceCatalog) -> bool:
    if not _safe_reference(evidence.reference):
        return False
    if evidence.evidence_type == "rule":
        return evidence.reference in catalog.rule_ids
    if evidence.evidence_type == "benchmark_case":
        return evidence.reference in catalog.benchmark_case_ids
    if evidence.evidence_type == "rejection_case":
        return evidence.reference in catalog.rejection_case_ids
    if evidence.evidence_type in {"reasoning_case", "golden_case"}:
        return evidence.reference in catalog.golden_case_ids
    if evidence.evidence_type in STATIC_EVIDENCE_REFERENCES:
        return evidence.reference in STATIC_EVIDENCE_REFERENCES[evidence.evidence_type]
    if evidence.evidence_type == "test":
        return evidence.reference.startswith("tests/") and evidence.reference.endswith(".py")
    if evidence.evidence_type == "documentation":
        return evidence.reference.startswith("docs/") or evidence.reference in {"README.md", "PROJECT_STATUS.md"}
    return False


def _evidence_key(evidence: EvidenceReference) -> tuple[str, str, str | None, str | None]:
    return (evidence.evidence_type, evidence.reference, evidence.family, evidence.stage)


def _all_evidence(capability: CapabilityDefinition) -> list[EvidenceReference]:
    return [*capability.implementation_evidence, *capability.verification_evidence]


def validate_capability_manifest(
    manifest: CapabilityManifest | None = None,
    *,
    catalog: EvidenceCatalog | None = None,
    rule_registry: RuleRegistry | None = None,
    pack_registry: RulePackRegistry | None = None,
) -> CapabilityValidationResult:
    """Validate capability declarations against known rules, packs, and evidence IDs."""

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    active_rule_registry = rule_registry or RuleRegistry.load()
    active_pack_registry = pack_registry or RulePackRegistry.load_default()
    active_catalog = catalog or build_evidence_catalog(rule_registry=active_rule_registry, pack_registry=active_pack_registry)

    try:
        active_manifest = manifest or load_capability_manifest()
    except CapabilityManifestError as exc:
        return CapabilityValidationResult(
            passed=False,
            capabilities_checked=0,
            errors=[{"message": str(exc)}],
            warnings=[],
            summary={},
        )

    capability_ids = [capability.capability_id for capability in active_manifest.capabilities]
    duplicate_capability_ids = sorted([item for item, count in Counter(capability_ids).items() if count > 1])
    for capability_id in duplicate_capability_ids:
        _add_error(errors, f"duplicate capability id: {capability_id}", capability_id=capability_id)

    mapped_rule_ids: set[str] = set()
    unknown_rule_refs: set[str] = set()
    unknown_pack_refs: set[str] = set()
    unknown_evidence: list[dict[str, Any]] = []
    duplicate_evidence: list[dict[str, Any]] = []
    supported_missing_impl: list[str] = []
    supported_missing_verification: list[str] = []
    partial_missing_limits: list[str] = []
    unsupported_missing_boundary: list[str] = []

    for capability in active_manifest.capabilities:
        for rule_id in capability.rule_ids:
            if rule_id not in active_catalog.rule_ids:
                unknown_rule_refs.add(rule_id)
                _add_error(errors, f"unknown rule reference: {rule_id}", capability_id=capability.capability_id, rule_id=rule_id)
            else:
                mapped_rule_ids.add(rule_id)
        for pack_id in capability.knowledge_packs:
            if pack_id not in active_catalog.pack_ids:
                unknown_pack_refs.add(pack_id)
                _add_error(errors, f"unknown pack reference: {pack_id}", capability_id=capability.capability_id, pack_id=pack_id)

        if capability.status == "supported":
            if not capability.implementation_evidence:
                supported_missing_impl.append(capability.capability_id)
                _add_error(errors, "supported capability missing implementation evidence", capability_id=capability.capability_id)
            if not capability.verification_evidence:
                supported_missing_verification.append(capability.capability_id)
                _add_error(errors, "supported capability missing verification evidence", capability_id=capability.capability_id)
        if capability.status == "partially_supported" and not capability.limitations:
            partial_missing_limits.append(capability.capability_id)
            _add_error(errors, "partially supported capability missing limitations", capability_id=capability.capability_id)
        if capability.status == "unsupported":
            rejection_evidence = [item for item in capability.verification_evidence if item.evidence_type == "rejection_case"]
            if not capability.rejection_behavior.strip() or not rejection_evidence:
                unsupported_missing_boundary.append(capability.capability_id)
                _add_error(
                    errors,
                    "unsupported capability missing rejection behavior or rejection evidence",
                    capability_id=capability.capability_id,
                )

        seen_evidence: set[tuple[str, str, str | None, str | None]] = set()
        for evidence in _all_evidence(capability):
            key = _evidence_key(evidence)
            if key in seen_evidence:
                entry = {
                    "capability_id": capability.capability_id,
                    "evidence_type": evidence.evidence_type,
                    "reference": evidence.reference,
                }
                duplicate_evidence.append(entry)
                _add_error(errors, "duplicate evidence reference", **entry)
            seen_evidence.add(key)
            if not _evidence_known(evidence, active_catalog):
                entry = {
                    "capability_id": capability.capability_id,
                    "evidence_type": evidence.evidence_type,
                    "reference": evidence.reference,
                }
                unknown_evidence.append(entry)
                _add_error(errors, "unknown evidence reference", **entry)

    active_rule_ids = {rule.id for rule in active_rule_registry.get_active_rules()}
    cross_cutting = dict(active_manifest.cross_cutting_rules)
    orphan_rule_ids = sorted(active_rule_ids - mapped_rule_ids - set(cross_cutting))
    for rule_id, reason in cross_cutting.items():
        if rule_id not in active_rule_ids:
            _add_error(errors, f"unknown cross-cutting rule: {rule_id}", rule_id=rule_id)
        if not reason.strip():
            _add_error(errors, "cross-cutting rule missing reason", rule_id=rule_id)
    for rule_id in orphan_rule_ids:
        _add_error(errors, f"active rule is not mapped to a capability: {rule_id}", rule_id=rule_id)

    return CapabilityValidationResult(
        passed=not errors,
        capabilities_checked=len(active_manifest.capabilities),
        errors=errors,
        warnings=warnings,
        summary={
            "duplicate_capability_id_count": len(duplicate_capability_ids),
            "unknown_rule_reference_count": len(unknown_rule_refs),
            "unknown_pack_reference_count": len(unknown_pack_refs),
            "unknown_evidence_reference_count": len(unknown_evidence),
            "duplicate_evidence_reference_count": len(duplicate_evidence),
            "active_rule_count": len(active_rule_ids),
            "mapped_active_rule_count": len(mapped_rule_ids & active_rule_ids),
            "orphan_active_rule_count": len(orphan_rule_ids),
            "supported_missing_implementation_count": len(supported_missing_impl),
            "supported_missing_verification_count": len(supported_missing_verification),
            "partial_missing_limitation_count": len(partial_missing_limits),
            "unsupported_missing_boundary_count": len(unsupported_missing_boundary),
            "orphan_active_rules": orphan_rule_ids,
            "supported_capabilities_missing_implementation_evidence": supported_missing_impl,
            "supported_capabilities_missing_verification_evidence": supported_missing_verification,
            "partial_capabilities_missing_limitations": partial_missing_limits,
            "unsupported_capabilities_missing_rejection_or_boundary_evidence": unsupported_missing_boundary,
            "unknown_rule_references": sorted(unknown_rule_refs),
            "unknown_pack_references": sorted(unknown_pack_refs),
            "unknown_evidence_references": unknown_evidence,
            "duplicate_capability_ids": duplicate_capability_ids,
            "duplicate_evidence_references": duplicate_evidence,
        },
    )


def build_capability_matrix(
    capabilities: Iterable[CapabilityDefinition] | None = None,
    *,
    pack_registry: RulePackRegistry | None = None,
    family: str | None = None,
    status: str | None = None,
    stage: str | None = None,
    knowledge_pack: str | None = None,
    rule_id: str | None = None,
    generated_at: str | None = None,
) -> CapabilityMatrix:
    """Build a deterministic, filterable capability matrix."""

    active_capabilities = list(capabilities or load_capability_manifest().capabilities)
    active_pack_registry = pack_registry or RulePackRegistry.load_default()
    rule_sources = active_pack_registry.rule_sources()
    rows: list[CapabilityMatrixRow] = []
    for capability in sorted(active_capabilities, key=lambda item: item.capability_id):
        derived_packs = sorted(
            set(capability.knowledge_packs)
            | {rule_sources[rule]["pack_id"] for rule in capability.rule_ids if rule in rule_sources}
        )
        row = CapabilityMatrixRow(
            capability_id=capability.capability_id,
            title=capability.title,
            family=capability.family,
            status=capability.status,
            stages=list(capability.stages),
            knowledge_packs=derived_packs,
            rule_ids=list(capability.rule_ids),
            implementation_evidence_count=len(capability.implementation_evidence),
            verification_evidence_count=len(capability.verification_evidence),
            limitations=list(capability.limitations),
            rejection_behavior=capability.rejection_behavior,
            provenance=dict(capability.provenance),
            version=capability.version,
        )
        if family and row.family != family:
            continue
        if status and row.status != status:
            continue
        if stage and stage not in row.stages:
            continue
        if knowledge_pack and knowledge_pack not in row.knowledge_packs:
            continue
        if rule_id and rule_id not in row.rule_ids:
            continue
        rows.append(row)

    summary = _summarize_rows(rows)
    identity = {
        "rows": [row.model_dump(mode="json") for row in rows],
        "filters": {
            "family": family,
            "status": status,
            "stage": stage,
            "knowledge_pack": knowledge_pack,
            "rule_id": rule_id,
        },
    }
    return CapabilityMatrix(
        matrix_id=stable_capability_digest("capability_matrix", identity),
        generated_at=generated_at or fixed_coverage_timestamp(),
        rows=rows,
        filters=identity["filters"],
        summary=summary,
    )


def _summarize_rows(rows: list[CapabilityMatrixRow]) -> dict[str, Any]:
    by_status = Counter(row.status for row in rows)
    by_family = Counter(row.family for row in rows)
    by_stage: Counter[str] = Counter()
    for row in rows:
        by_stage.update(row.stages)
    return {
        "capability_count": len(rows),
        "by_status": dict(sorted(by_status.items())),
        "by_family": dict(sorted(by_family.items())),
        "by_stage": dict(sorted(by_stage.items())),
    }


def build_coverage_report(
    manifest: CapabilityManifest | None = None,
    *,
    rule_registry: RuleRegistry | None = None,
    pack_registry: RulePackRegistry | None = None,
    generated_at: str | None = None,
) -> CoverageReport:
    """Build a deterministic coverage report for the capability manifest."""

    active_manifest = manifest or load_capability_manifest()
    active_rule_registry = rule_registry or RuleRegistry.load()
    active_pack_registry = pack_registry or RulePackRegistry.load_default()
    validation = validate_capability_manifest(
        active_manifest,
        rule_registry=active_rule_registry,
        pack_registry=active_pack_registry,
    )
    matrix = build_capability_matrix(active_manifest.capabilities, pack_registry=active_pack_registry, generated_at=generated_at)
    rows = matrix.rows
    status_counts = Counter(row.status for row in rows)
    per_family: dict[str, dict[str, int]] = {}
    for family_name in SUPPORTED_CAPABILITY_FAMILIES:
        family_rows = [row for row in rows if row.family == family_name]
        family_counts = Counter(row.status for row in family_rows)
        per_family[family_name] = {
            "total": len(family_rows),
            "supported": family_counts.get("supported", 0),
            "partially_supported": family_counts.get("partially_supported", 0),
            "unsupported": family_counts.get("unsupported", 0),
            "not_applicable": family_counts.get("not_applicable", 0),
        }
    per_stage: dict[str, dict[str, int]] = {}
    for stage_name in SUPPORTED_CAPABILITY_STAGES:
        stage_rows = [row for row in rows if stage_name in row.stages]
        stage_counts = Counter(row.status for row in stage_rows)
        per_stage[stage_name] = {
            "total": len(stage_rows),
            "supported": stage_counts.get("supported", 0),
            "partially_supported": stage_counts.get("partially_supported", 0),
            "unsupported": stage_counts.get("unsupported", 0),
            "not_applicable": stage_counts.get("not_applicable", 0),
        }

    supported = [cap for cap in active_manifest.capabilities if cap.status == "supported"]
    implementation_complete = sum(1 for cap in supported if cap.implementation_evidence)
    verification_complete = sum(1 for cap in supported if cap.verification_evidence)
    denominator = len(supported) or 1
    summary = validation.summary
    report_payload = {
        "manifest_version": active_manifest.manifest_version,
        "matrix_id": matrix.matrix_id,
        "validation_summary": summary,
        "per_family": per_family,
        "per_stage": per_stage,
    }
    report_id = stable_capability_digest("coverage", report_payload)
    return CoverageReport(
        report_id=report_id,
        generated_at=generated_at or fixed_coverage_timestamp(),
        declared_capability_count=len(rows),
        supported_capability_count=status_counts.get("supported", 0),
        partially_supported_capability_count=status_counts.get("partially_supported", 0),
        unsupported_capability_count=status_counts.get("unsupported", 0),
        not_applicable_capability_count=status_counts.get("not_applicable", 0),
        active_rule_count=int(summary.get("active_rule_count", 0)),
        mapped_active_rule_count=int(summary.get("mapped_active_rule_count", 0)),
        orphan_active_rule_count=int(summary.get("orphan_active_rule_count", 0)),
        implementation_evidence_completeness=implementation_complete / denominator,
        verification_evidence_completeness=verification_complete / denominator,
        supported_capabilities_missing_implementation_evidence=list(summary.get("supported_capabilities_missing_implementation_evidence", [])),
        supported_capabilities_missing_verification_evidence=list(summary.get("supported_capabilities_missing_verification_evidence", [])),
        partial_capabilities_missing_limitations=list(summary.get("partial_capabilities_missing_limitations", [])),
        unsupported_capabilities_missing_rejection_or_boundary_evidence=list(summary.get("unsupported_capabilities_missing_rejection_or_boundary_evidence", [])),
        unknown_rule_references=list(summary.get("unknown_rule_references", [])),
        unknown_pack_references=list(summary.get("unknown_pack_references", [])),
        unknown_evidence_references=list(summary.get("unknown_evidence_references", [])),
        duplicate_capability_ids=list(summary.get("duplicate_capability_ids", [])),
        duplicate_evidence_references=list(summary.get("duplicate_evidence_references", [])),
        orphan_active_rules=list(summary.get("orphan_active_rules", [])),
        cross_cutting_rules=dict(active_manifest.cross_cutting_rules),
        per_family=per_family,
        per_stage=per_stage,
        matrix=rows,
        validation_errors=validation.errors,
        validation_warnings=validation.warnings,
        passed=validation.passed,
    )


def write_coverage_report(report: CoverageReport, path: str) -> None:
    """Write a coverage report as stable JSON."""

    from pathlib import Path

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_json(), encoding="utf-8")


def write_capability_matrix(matrix: CapabilityMatrix, path: str) -> None:
    """Write a capability matrix as stable JSON."""

    from pathlib import Path

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(matrix.to_json(), encoding="utf-8")
