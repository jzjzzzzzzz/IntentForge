"""Technical harness orchestrator and quality gates."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import shutil
from typing import Any

import yaml

from benchmark.run_benchmark import run_benchmark
from harness.adversarial import run_adversarial_harness
from harness.edits import run_edit_preservation_harness
from harness.sweeps import run_parametric_sweep
from harness.topology import (
    build_volume_delta_report,
    inspect_shape,
    recognize_features,
    write_feature_recognition_report,
    write_feature_recognition_summary,
    write_shape_inspection_report,
)
from intentforge.generator.cadquery_generator import (
    CadQueryUnavailableError,
    build_l_bracket,
    build_wall_bracket,
)
from intentforge.output_manager import create_run_context, feature_state_names, json_safe_paths
from intentforge.paths import project_root as _intentforge_project_root
from intentforge.schemas import ParameterTable
from intentforge.knowledge import (
    RulePackRegistry,
    RuleRegistry,
    build_coverage_report,
    build_design_metrics,
    build_engineering_reasoning_report,
    generate_trust_report,
    evaluate_parameter_table,
    make_knowledge_report,
    resolve_evidence,
    validate_default_rule_packs,
    validate_evidence_manifest,
    validate_rule_data,
)
from intentforge.knowledge.reasoning.benchmark import run_reasoning_benchmark
from intentforge.assurance import (
    attach_assurance_predecessor,
    build_assurance_case,
    build_audit_package,
    validate_assurance_case,
)
from intentforge.assurance.schema import AssuranceCase
from intentforge.review import (
    ReviewEvaluationError,
    collect_review_evaluation_resources,
    diff_review_decisions,
    diff_review_variants,
    evaluate_assurance_case,
    get_review_policy,
    load_review_policies,
    validate_review_decision,
    validate_review_policy,
    validate_review_policy_manifest,
    verify_decision_provenance,
    verify_offline_audit_package,
    cas_storage_path,
    store_audit_package,
    verify_audit_chain,
)
from intentforge.review.portability import (
    canonical_json_bytes,
    normalize_portable_data,
    portability_violations,
)
from intentforge.workflows import edit_parse_apply_workflow, parse_build_workflow

SUPPORTED_MODEL_FAMILIES = ("wall_mounted_bracket", "l_bracket")

QUALITY_GATES: dict[str, float | int] = {
    "benchmark_pass_rate_min": 0.95,
    "sweep_pass_rate_min": 0.95,
    "edit_preservation_rate_min": 0.95,
    "adversarial_rejection_success_rate_min": 1.0,
    "unexpected_failure_count_max": 0,
    "unsafe_acceptance_count_max": 0,
    "unexpected_exception_count_max": 0,
    "reasoning_generation_pass_rate_min": 1.0,
    "unknown_rule_reference_count_max": 0,
    "duplicate_recommendation_count_max": 0,
    "missing_limitation_count_max": 0,
    "recommendation_contradiction_count_max": 0,
    "recommendation_applicability_error_count_max": 0,
    "nondeterministic_reasoning_report_count_max": 0,
    "reasoning_report_id_mismatch_count_max": 0,
    "rule_pack_load_pass_rate_min": 1.0,
    "active_pack_count_min": 4,
    "active_pack_count_max": 4,
    "active_rule_count_min": 10,
    "active_rule_count_max": 10,
    "duplicate_pack_id_count_max": 0,
    "duplicate_rule_id_count_max": 0,
    "invalid_pack_count_max": 0,
    "rule_pack_unknown_rule_reference_count_max": 0,
    "legacy_compatibility_passed_min": 1,
    "rule_pack_reasoning_regression_pass_rate_min": 1.0,
    "capability_manifest_valid_min": 1,
    "capability_duplicate_id_count_max": 0,
    "capability_unknown_reference_count_max": 0,
    "capability_supported_missing_implementation_count_max": 0,
    "capability_supported_missing_verification_count_max": 0,
    "capability_partial_missing_limitation_count_max": 0,
    "capability_unsupported_missing_boundary_count_max": 0,
    "capability_orphan_rule_count_max": 0,
    "capability_nondeterministic_report_count_max": 0,
    "evidence_manifest_valid_min": 1,
    "evidence_duplicate_id_count_max": 0,
    "evidence_unknown_capability_reference_count_max": 0,
    "evidence_unknown_rule_reference_count_max": 0,
    "evidence_unknown_pack_reference_count_max": 0,
    "evidence_unsafe_file_reference_count_max": 0,
    "evidence_family_mismatch_count_max": 0,
    "evidence_stage_mismatch_count_max": 0,
    "evidence_supported_missing_implementation_count_max": 0,
    "evidence_supported_missing_verification_count_max": 0,
    "evidence_partial_missing_limitation_count_max": 0,
    "evidence_unsupported_missing_boundary_count_max": 0,
    "evidence_orphan_count_max": 0,
    "evidence_deterministic_bundle_mismatch_count_max": 0,
    "evidence_deterministic_trust_report_mismatch_count_max": 0,
    "assurance_gate_passed_min": 1,
    "assurance_invalid_capability_reference_count_max": 0,
    "assurance_invalid_evidence_reference_count_max": 0,
    "assurance_invalid_rule_reference_count_max": 0,
    "assurance_unsafe_artifact_path_count_max": 0,
    "assurance_missing_required_validation_count_max": 0,
    "assurance_deterministic_case_mismatch_count_max": 0,
    "assurance_deterministic_package_mismatch_count_max": 0,
    "assurance_package_hash_mismatch_count_max": 0,
    "review_gate_passed_min": 1,
    "review_policy_manifest_valid_min": 1,
    "review_invalid_policy_count_max": 0,
    "review_unknown_claim_reference_count_max": 0,
    "review_unknown_validation_reference_count_max": 0,
    "review_unknown_capability_reference_count_max": 0,
    "review_unknown_evidence_reference_count_max": 0,
    "review_unknown_rule_reference_count_max": 0,
    "review_policy_scope_mismatch_count_max": 0,
    "review_unsafe_path_count_max": 0,
    "review_deterministic_finding_mismatch_count_max": 0,
    "review_deterministic_condition_mismatch_count_max": 0,
    "review_deterministic_decision_mismatch_count_max": 0,
    "review_audit_package_hash_mismatch_count_max": 0,
    "review_expected_decision_mismatch_count_max": 0,
    "review_full_policy_incompatible_acceptance_count_max": 0,
    "review_provenance_missing_count_max": 0,
    "review_provenance_snapshot_mismatch_count_max": 0,
    "review_provenance_execution_node_mismatch_count_max": 0,
    "review_provenance_replay_mismatch_count_max": 0,
    "review_provenance_evidence_matrix_mismatch_count_max": 0,
    "review_deterministic_provenance_mismatch_count_max": 0,
    "review_semantic_diff_generation_failure_count_max": 0,
    "review_semantic_diff_deterministic_mismatch_count_max": 0,
    "review_multi_variant_diff_deterministic_mismatch_count_max": 0,
    "review_offline_verification_pass_count_min": 5,
    "review_offline_assurance_claim_count_min": 49,
    "review_offline_assurance_claim_count_max": 49,
    "review_offline_evidence_matrix_mismatch_count_max": 0,
    "review_offline_policy_catalog_mismatch_count_max": 0,
    "review_offline_static_replay_mismatch_count_max": 0,
    "review_offline_hash_mismatch_count_max": 0,
    "review_portability_violation_count_max": 0,
    "review_cross_platform_portability_mismatch_count_max": 0,
    "review_cas_store_failure_count_max": 0,
    "review_cas_object_hash_mismatch_count_max": 0,
    "review_cas_deterministic_mismatch_count_max": 0,
    "review_predecessor_embedding_mismatch_count_max": 0,
    "review_chain_validation_pass_count_min": 1,
    "review_chain_length_min": 3,
    "review_chain_tamper_detection_pass_count_min": 3,
    "review_chain_pointer_mismatch_count_max": 0,
    "review_chain_missing_predecessor_count_max": 0,
}


def _project_root() -> Path:
    return _intentforge_project_root()


def _cadquery_available() -> bool:
    return importlib.util.find_spec("cadquery") is not None


def _require_cadquery() -> None:
    if not _cadquery_available():
        raise CadQueryUnavailableError(
            "CadQuery is required to run the technical harness because it builds, "
            "inspects, and validates real CAD models. Install it with: "
            "python -m pip install -e '.[cad]'"
        )


def _write_json(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _load_example_parameters(family: str) -> ParameterTable:
    filenames = {
        "wall_mounted_bracket": "bracket_params.yaml",
        "l_bracket": "l_bracket_params.yaml",
    }
    if family not in filenames:
        raise ValueError(f"Unsupported model family: {family}")
    path = _project_root() / "examples" / filenames[family]
    return ParameterTable.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def _build_example_model(parameter_table: ParameterTable) -> Any:
    if parameter_table.family == "l_bracket":
        return build_l_bracket(parameter_table)
    if parameter_table.family == "wall_mounted_bracket":
        return build_wall_bracket(parameter_table)
    raise ValueError(f"Unsupported model family: {parameter_table.family}")


def _run_section(name: str, runner: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started_at = datetime.now().astimezone().isoformat()
    try:
        section = runner()
        return {
            "name": name,
            "passed": bool(section.get("passed", False)),
            "started_at": started_at,
            "completed_at": datetime.now().astimezone().isoformat(),
            **section,
        }
    except Exception as exc:  # pragma: no cover - exercised through integration failures
        return {
            "name": name,
            "passed": False,
            "started_at": started_at,
            "completed_at": datetime.now().astimezone().isoformat(),
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }


def _benchmark_section(output_root: Path) -> dict[str, Any]:
    result = run_benchmark(output_root=output_root)
    return {
        "passed": result["failed"] == 0,
        "run_id": result["run_id"],
        "total_cases": result["total_cases"],
        "passed_cases": result["passed"],
        "failed_cases": result["failed"],
        "pass_rate": result["pass_rate"],
        "families": result["families"],
        "categories": result["categories"],
        "report_path": result["report_path"],
        "summary_path": result["summary_path"],
        "persistent_output_dir": result["run_dir"],
    }


def _sweep_section(output_root: Path, *, quick: bool) -> dict[str, Any]:
    result = run_parametric_sweep(
        output_root,
        max_cases_per_family=10 if quick else 30,
        export_enabled=True,
    )
    return {
        "passed": result["failed"] == 0,
        "run_id": result["run_id"],
        "total_cases": result["total_cases"],
        "passed_cases": result["passed"],
        "failed_cases": result["failed"],
        "pass_rate": result["pass_rate"],
        "families": result["families"],
        "failure_types": result["failure_types"],
        "report_path": result["report_path"],
        "summary_path": result["summary_path"],
        "persistent_output_dir": result["persistent_output_dir"],
    }


def _edit_preservation_section(output_root: Path) -> dict[str, Any]:
    result = run_edit_preservation_harness(output_root, export_enabled=True)
    return {
        "passed": result["failed_chains"] == 0 and result["failed_steps"] == 0,
        "run_id": result["run_id"],
        "total_chains": result["total_chains"],
        "passed_chains": result["passed_chains"],
        "failed_chains": result["failed_chains"],
        "total_edit_steps": result["total_edit_steps"],
        "passed_steps": result["passed_steps"],
        "failed_steps": result["failed_steps"],
        "edit_preservation_rate": result["edit_preservation_rate"],
        "families": result["families"],
        "failure_types": result["failure_types"],
        "report_path": result["report_path"],
        "summary_path": result["summary_path"],
        "persistent_output_dir": result["persistent_output_dir"],
    }


def _adversarial_section(output_root: Path) -> dict[str, Any]:
    result = run_adversarial_harness(output_root)
    return {
        "passed": result["failed"] == 0,
        "run_id": result["run_id"],
        "total_cases": result["total_cases"],
        "passed_cases": result["passed"],
        "failed_cases": result["failed"],
        "rejection_success_rate": result["rejection_success_rate"],
        "categories": result["categories"],
        "failure_types": result["failure_types"],
        "report_path": result["report_path"],
        "summary_path": result["summary_path"],
        "persistent_output_dir": result["persistent_output_dir"],
    }


def _volume_delta_section(run_dir: Path) -> dict[str, Any]:
    volume_dir = run_dir / "volume_delta"
    reports: dict[str, dict[str, Any]] = {}
    failed_families: list[str] = []

    for family in SUPPORTED_MODEL_FAMILIES:
        parameter_table = _load_example_parameters(family)
        model = _build_example_model(parameter_table)
        active_features, omitted_features = feature_state_names(parameter_table)
        report_path = volume_dir / f"{family}_volume_delta_report.json"
        report = build_volume_delta_report(
            parameter_table,
            model,
            run_id=f"{run_dir.name}_{family}",
            active_features=active_features,
            omitted_features=omitted_features,
            output_paths={"persistent_report": str(report_path)},
        )
        _write_json(report, report_path)
        if not report["passed"]:
            failed_families.append(family)
        reports[family] = {
            "passed": report["passed"],
            "active_features": report["active_features"],
            "omitted_features": report["omitted_features"],
            "feature_volume_mm3": report["feature_volume_mm3"],
            "check_count": len(report["checks"]),
            "failed_checks": report["failed_checks"],
            "warnings": report["warnings"],
            "report_path": str(report_path),
        }

    return {
        "passed": not failed_families,
        "families": reports,
        "failed_families": failed_families,
    }


def _shape_inspection_section(run_dir: Path) -> dict[str, Any]:
    shape_dir = run_dir / "shape_inspection"
    reports: dict[str, dict[str, Any]] = {}
    failed_families: list[str] = []

    for family in SUPPORTED_MODEL_FAMILIES:
        parameter_table = _load_example_parameters(family)
        model = _build_example_model(parameter_table)
        report = inspect_shape(model, family=family)
        report_path = shape_dir / f"{family}_topology_report.json"
        write_shape_inspection_report(report, report_path)
        passed = (
            report.bounding_box_dimensions_mm is not None
            and report.volume_mm3 is not None
            and report.is_valid is not False
        )
        if not passed:
            failed_families.append(family)
        reports[family] = {
            "passed": passed,
            "bounding_box_dimensions_mm": report.bounding_box_dimensions_mm,
            "volume_mm3": report.volume_mm3,
            "solid_count": report.solid_count,
            "face_count": report.face_count,
            "edge_count": report.edge_count,
            "vertex_count": report.vertex_count,
            "is_valid": report.is_valid,
            "warning_count": len(report.warnings),
            "warnings": [warning.model_dump(mode="json") for warning in report.warnings],
            "report_path": str(report_path),
        }

    return {
        "passed": not failed_families,
        "families": reports,
        "failed_families": failed_families,
    }


def _feature_recognition_section(run_dir: Path) -> dict[str, Any]:
    recognition_dir = run_dir / "feature_recognition"
    reports: dict[str, dict[str, Any]] = {}
    warning_count = 0
    failed_families: list[str] = []

    for family in SUPPORTED_MODEL_FAMILIES:
        parameter_table = _load_example_parameters(family)
        model = _build_example_model(parameter_table)
        report = recognize_features(model, parameter_table)
        report_path = recognition_dir / f"{family}_feature_recognition_report.json"
        summary_path = recognition_dir / f"{family}_feature_recognition_summary.txt"
        write_feature_recognition_report(report, report_path)
        write_feature_recognition_summary(report, summary_path)
        warning_count += len(report.get("warnings", []) or [])
        if not report.get("passed", False):
            failed_families.append(family)
        reports[family] = {
            "passed": bool(report.get("passed", False)),
            "warning_count": len(report.get("warnings", []) or []),
            "recognized_features": report.get("recognized_features", {}),
            "topology_checks": report.get("topology_checks", {}),
            "report_path": str(report_path),
            "summary_path": str(summary_path),
        }

    pass_rate = (len(SUPPORTED_MODEL_FAMILIES) - len(failed_families)) / len(SUPPORTED_MODEL_FAMILIES)
    return {
        "passed": True,
        "warning_only": True,
        "pass_rate": pass_rate,
        "warning_count": warning_count,
        "families": reports,
        "failed_families": failed_families,
    }


def _reasoning_section(run_dir: Path) -> dict[str, Any]:
    reasoning_dir = run_dir / "engineering_reasoning"
    registry = RuleRegistry.load()
    known_rule_ids = {rule.id for rule in registry.rules}
    family_reports: dict[str, dict[str, Any]] = {}
    unknown_rule_reference_count = 0
    duplicate_recommendation_count = 0
    missing_limitation_count = 0
    failed_families: list[str] = []

    for family in SUPPORTED_MODEL_FAMILIES:
        parameter_table = _load_example_parameters(family)
        # Feature plan is not required for this lightweight reasoning check.
        findings = evaluate_parameter_table(parameter_table)
        knowledge_report = make_knowledge_report(findings, rules_checked=registry.count(), timestamp="2026-07-10T00:00:00+00:00")
        metrics = build_design_metrics(parameter_table)
        report = build_engineering_reasoning_report(
            model_family=family,
            knowledge_report=knowledge_report,
            rule_registry=registry,
            metrics=metrics,
            parameters={parameter.name: parameter.value for parameter in parameter_table.parameters},
            timestamp="2026-07-10T00:00:00+00:00",
        )
        repeat = build_engineering_reasoning_report(
            model_family=family,
            knowledge_report=knowledge_report,
            rule_registry=registry,
            metrics=metrics,
            parameters={parameter.name: parameter.value for parameter in parameter_table.parameters},
            timestamp="2026-07-10T00:00:00+00:00",
        )
        report_path = reasoning_dir / f"{family}_engineering_reasoning_report.json"
        _write_json(report.model_dump(mode="json"), report_path)

        referenced_rule_ids: set[str] = set()
        for collection_name in ("observations", "interactions", "conflicts", "recommendations"):
            collection = getattr(report, collection_name)
            for item in collection:
                referenced_rule_ids.update(getattr(item, "rule_ids", []))
        for tradeoff in report.tradeoffs:
            referenced_rule_ids.update(tradeoff.source_rule_ids)
        unknown = sorted(referenced_rule_ids - known_rule_ids)
        unknown_rule_reference_count += len(unknown)

        recommendation_ids = [recommendation.recommendation_id for recommendation in report.recommendations]
        duplicate_recommendation_count += len(recommendation_ids) - len(set(recommendation_ids))
        if not report.limitations:
            missing_limitation_count += 1
        missing_limitation_count += len([recommendation for recommendation in report.recommendations if not recommendation.limitations])

        passed = (
            report.report_id == repeat.report_id
            and not unknown
            and len(recommendation_ids) == len(set(recommendation_ids))
            and bool(report.limitations)
        )
        if not passed:
            failed_families.append(family)
        family_reports[family] = {
            "passed": passed,
            "report_id": report.report_id,
            "deterministic_report_id": report.report_id == repeat.report_id,
            "unknown_rule_references": unknown,
            "recommendation_count": len(report.recommendations),
            "interaction_count": len(report.interactions),
            "conflict_count": len(report.conflicts),
            "report_path": str(report_path),
        }

    benchmark = run_reasoning_benchmark(rule_registry=registry)
    if benchmark["failed"] > 0:
        failed_families.append("reasoning_benchmark")

    total_checks = len(SUPPORTED_MODEL_FAMILIES) + benchmark["total_cases"]
    failed_checks = len([family for family in SUPPORTED_MODEL_FAMILIES if not family_reports[family]["passed"]]) + benchmark["failed"]
    pass_rate = (total_checks - failed_checks) / total_checks if total_checks else 0.0
    return {
        "passed": failed_checks == 0,
        "pass_rate": pass_rate,
        "families": family_reports,
        "reasoning_benchmark": benchmark,
        "failed_families": failed_families,
        "unknown_rule_reference_count": unknown_rule_reference_count + benchmark["unknown_rule_reference_count"],
        "duplicate_recommendation_count": duplicate_recommendation_count + benchmark["duplicate_recommendation_count"],
        "missing_limitation_count": missing_limitation_count + benchmark["missing_limitation_count"],
        "recommendation_contradiction_count": benchmark["contradiction_count"],
        "recommendation_applicability_error_count": benchmark["applicability_error_count"],
        "nondeterministic_reasoning_report_count": benchmark["nondeterministic_report_count"],
        "reasoning_report_id_mismatch_count": benchmark["report_id_mismatch_count"],
    }


def _rule_pack_section(run_dir: Path) -> dict[str, Any]:
    pack_dir = run_dir / "rule_packs"
    pack_registry = RulePackRegistry.load_default()
    rule_registry = RuleRegistry.load()
    validation = validate_default_rule_packs()
    legacy_validation = validate_rule_data()
    pack_rule_ids = [rule.id for rule in pack_registry.flatten_rules()]
    legacy_rule_ids = [rule.id for rule in rule_registry.rules]
    legacy_compatibility_passed = pack_rule_ids == legacy_rule_ids and legacy_validation["ok"]
    reasoning_regression = run_reasoning_benchmark(rule_registry=rule_registry)
    invalid_pack_count = 0 if validation.passed else 1

    report = {
        "passed": (
            validation.passed
            and legacy_compatibility_passed
            and reasoning_regression["failed"] == 0
        ),
        "active_pack_count": len(pack_registry.get_active_packs()),
        "active_rule_count": pack_registry.count_rules(),
        "duplicate_pack_id_count": int(validation.summary.get("duplicate_pack_id_count", 0)),
        "duplicate_rule_id_count": int(validation.summary.get("duplicate_rule_id_count", 0)),
        "invalid_pack_count": invalid_pack_count,
        "unknown_rule_reference_count": int(validation.summary.get("unknown_rule_reference_count", 0)),
        "legacy_compatibility_passed": legacy_compatibility_passed,
        "reasoning_regression_pass_rate": reasoning_regression["pass_rate"],
        "packs_checked": validation.packs_checked,
        "rules_checked": validation.rules_checked,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "rule_sources": pack_registry.rule_sources(),
        "reasoning_regression": reasoning_regression,
    }
    report_path = pack_dir / "rule_pack_validation_report.json"
    _write_json(report, report_path)
    report["report_path"] = str(report_path)
    return report


def _capability_coverage_section(run_dir: Path) -> dict[str, Any]:
    coverage_dir = run_dir / "capability_coverage"
    first_report = build_coverage_report()
    second_report = build_coverage_report()
    nondeterministic_count = 0 if first_report.report_id == second_report.report_id else 1
    report_data = first_report.model_dump(mode="json")
    unknown_reference_count = (
        len(first_report.unknown_rule_references)
        + len(first_report.unknown_pack_references)
        + len(first_report.unknown_evidence_references)
    )
    result = {
        "passed": first_report.passed and nondeterministic_count == 0,
        "capability_manifest_valid": first_report.passed,
        "capability_count": first_report.declared_capability_count,
        "supported_capability_count": first_report.supported_capability_count,
        "partial_capability_count": first_report.partially_supported_capability_count,
        "unsupported_capability_count": first_report.unsupported_capability_count,
        "active_rule_count": first_report.active_rule_count,
        "mapped_rule_count": first_report.mapped_active_rule_count,
        "orphan_rule_count": first_report.orphan_active_rule_count,
        "unknown_reference_count": unknown_reference_count,
        "duplicate_capability_id_count": len(first_report.duplicate_capability_ids),
        "duplicate_evidence_reference_count": len(first_report.duplicate_evidence_references),
        "supported_missing_implementation_count": len(first_report.supported_capabilities_missing_implementation_evidence),
        "supported_missing_verification_count": len(first_report.supported_capabilities_missing_verification_evidence),
        "partial_missing_limitation_count": len(first_report.partial_capabilities_missing_limitations),
        "unsupported_missing_boundary_count": len(first_report.unsupported_capabilities_missing_rejection_or_boundary_evidence),
        "implementation_evidence_completeness": first_report.implementation_evidence_completeness,
        "verification_evidence_completeness": first_report.verification_evidence_completeness,
        "nondeterministic_report_count": nondeterministic_count,
        "coverage_gate_passed": first_report.passed and nondeterministic_count == 0,
        "coverage_report": report_data,
    }
    report_path = coverage_dir / "capability_coverage_report.json"
    _write_json(result, report_path)
    result["report_path"] = str(report_path)
    return result


def _evidence_trust_section(run_dir: Path) -> dict[str, Any]:
    evidence_dir = run_dir / "evidence_trust"
    validation = validate_evidence_manifest()
    resolution = resolve_evidence()
    first_report = generate_trust_report()
    second_report = generate_trust_report()
    first_bundle_ids = [bundle.bundle_id for bundle in first_report.bundles]
    second_bundle_ids = [bundle.bundle_id for bundle in second_report.bundles]
    deterministic_bundle_mismatch_count = 0 if first_bundle_ids == second_bundle_ids else 1
    deterministic_report_mismatch_count = 0 if first_report.report_id == second_report.report_id else 1
    validation_summary = validation.summary
    result = {
        "passed": (
            validation.passed
            and first_report.overall_trust_gate_passed
            and deterministic_bundle_mismatch_count == 0
            and deterministic_report_mismatch_count == 0
        ),
        "evidence_manifest_valid": validation.passed,
        "evidence_definition_count": first_report.total_evidence_definition_count,
        "required_evidence_count": first_report.required_evidence_count,
        "verified_evidence_count": first_report.verified_evidence_count,
        "failed_evidence_count": first_report.failed_evidence_count,
        "unresolved_evidence_count": first_report.unresolved_evidence_count,
        "unavailable_evidence_count": first_report.unavailable_evidence_count,
        "stale_evidence_count": first_report.stale_evidence_count,
        "orphan_evidence_count": first_report.orphan_evidence_count,
        "duplicate_evidence_id_count": first_report.duplicate_evidence_id_count,
        "duplicate_reference_count": first_report.duplicate_normalized_reference_count,
        "family_mismatch_count": first_report.family_mismatch_count,
        "stage_mismatch_count": first_report.stage_mismatch_count,
        "unknown_capability_reference_count": first_report.unknown_capability_reference_count,
        "unknown_rule_reference_count": first_report.unknown_rule_reference_count,
        "unknown_pack_reference_count": first_report.unknown_pack_reference_count,
        "unsafe_file_reference_count": int(validation_summary.get("unsafe_file_reference_count", 0)),
        "supported_missing_implementation_count": int(validation_summary.get("supported_missing_implementation_count", 0)),
        "supported_missing_verification_count": int(validation_summary.get("supported_missing_verification_count", 0)),
        "partial_missing_limitation_count": int(validation_summary.get("partial_missing_limitation_count", 0)),
        "unsupported_missing_boundary_count": int(validation_summary.get("unsupported_missing_boundary_count", 0)),
        "supported_capability_bundle_count": first_report.supported_capability_count,
        "supported_capabilities_with_complete_evidence": len(first_report.supported_capabilities_with_complete_evidence),
        "supported_capabilities_with_incomplete_evidence": len(first_report.supported_capabilities_with_incomplete_evidence),
        "partial_capabilities_with_limitation_evidence": len(first_report.partially_supported_capabilities_with_complete_limitation_evidence),
        "unsupported_boundaries_with_rejection_evidence": len(first_report.unsupported_boundaries_with_verified_rejection_evidence),
        "implementation_evidence_completeness": first_report.implementation_evidence_completeness,
        "verification_evidence_completeness": first_report.verification_evidence_completeness,
        "boundary_evidence_completeness": first_report.boundary_evidence_completeness,
        "limitation_evidence_completeness": first_report.limitation_evidence_completeness,
        "deterministic_bundle_mismatch_count": deterministic_bundle_mismatch_count,
        "deterministic_report_mismatch_count": deterministic_report_mismatch_count,
        "trust_gate_passed": first_report.overall_trust_gate_passed,
        "resolution_report_id": resolution.report_id,
        "trust_report": first_report.model_dump(mode="json"),
        "validation_errors": validation.errors,
        "validation_warnings": validation.warnings,
    }
    report_path = evidence_dir / "evidence_trust_report.json"
    _write_json(result, report_path)
    result["report_path"] = str(report_path)
    return result


def _assurance_section(run_dir: Path) -> dict[str, Any]:
    assurance_dir = run_dir / "assurance"
    fixture_root = assurance_dir / "fixture_outputs"
    workflows = [
        ("wall_build", parse_build_workflow(
            "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
            fixture_root / "wall", dry_run=True, request_id="assurance_fixture_wall"), "standard"),
        ("l_build", parse_build_workflow(
            "Make an L-bracket 80 mm wide with 60 mm legs, 8 mm thick, and two holes on each leg.",
            fixture_root / "l", dry_run=True, request_id="assurance_fixture_l"), "standard"),
        ("partial_feature", parse_build_workflow(
            "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with rounded corners and two holes.",
            fixture_root / "partial", dry_run=True, request_id="assurance_fixture_partial"), "standard"),
        ("rejected", parse_build_workflow(
            "Make a gear with 24 teeth.", fixture_root / "rejected", dry_run=True,
            request_id="assurance_fixture_rejected"), "static"),
        ("edit", edit_parse_apply_workflow(
            "bracket", "Make it 150 mm wide but keep the same thickness.", fixture_root / "edit",
            dry_run=True, request_id="assurance_fixture_edit"), "standard"),
    ]
    cases = []
    validation_pass_count = 0
    aggregate = {"invalid_capability_reference_count": 0, "invalid_evidence_reference_count": 0,
                 "invalid_rule_reference_count": 0, "unsafe_artifact_path_count": 0,
                 "missing_required_validation_count": 0}
    deterministic_case_mismatch_count = 0
    deterministic_package_mismatch_count = 0
    package_hash_mismatch_count = 0
    package_validation_pass_count = 0
    fixture_case_paths: dict[str, str] = {}
    for name, workflow_result, profile in workflows:
        if name == "rejected": workflow_result["object_type"] = "wall_mounted_bracket"
        case = build_assurance_case(workflow_result, profile=profile, input_request=name)
        duplicate = build_assurance_case(workflow_result, profile=profile, input_request=name)
        deterministic_case_mismatch_count += int(case.assurance_case_id != duplicate.assurance_case_id)
        validation = validate_assurance_case(case)
        validation_pass_count += int(validation.passed)
        for key in aggregate: aggregate[key] += int(validation.metrics.get(key, 0))
        first = build_audit_package(case, assurance_dir / "packages" / f"{name}_a")
        second = build_audit_package(case, assurance_dir / "packages" / f"{name}_b")
        deterministic_package_mismatch_count += int(first["package_id"] != second["package_id"])
        package_validation_pass_count += int(first["validation"]["passed"])
        package_hash_mismatch_count += int(first["validation"].get("hash_mismatch_count", 0))
        case_path = assurance_dir / "cases" / f"{name}.json"
        _write_json(case.model_dump(mode="json"), case_path)
        fixture_case_paths[name] = str(case_path)
        cases.append(case)
    claims = [claim for case in cases for claim in case.claims]
    result = {
        "passed": validation_pass_count == len(cases) and not any(aggregate.values())
                  and deterministic_case_mismatch_count == 0 and deterministic_package_mismatch_count == 0
                  and package_hash_mismatch_count == 0,
        "assurance_schema_valid": validation_pass_count == len(cases), "assurance_fixture_count": len(workflows),
        "assurance_case_count": len(cases), "assurance_case_validation_pass_count": validation_pass_count,
        "assurance_claim_count": len(claims), "supported_claim_count": sum(c.status == "supported" for c in claims),
        "partial_claim_count": sum(c.status == "partially_supported" for c in claims),
        "failed_claim_count": sum(c.status == "failed" for c in claims),
        "unresolved_claim_count": sum(c.status == "unresolved" for c in claims),
        **aggregate, "unsupported_boundary_disclosure_count": sum(bool(c.limitations) for c in cases),
        "limitation_disclosure_count": sum(len(c.limitations) for c in cases),
        "audit_package_validation_pass_count": package_validation_pass_count,
        "audit_package_hash_mismatch_count": package_hash_mismatch_count,
        "deterministic_assurance_case_mismatch_count": deterministic_case_mismatch_count,
        "deterministic_audit_package_mismatch_count": deterministic_package_mismatch_count,
        "fixture_case_paths": fixture_case_paths,
    }
    result["assurance_gate_passed"] = result["passed"]
    report_path = assurance_dir / "assurance_harness_report.json"
    _write_json(result, report_path)
    result["report_path"] = str(report_path)
    return result


def _cross_platform_portability_check(case: AssuranceCase) -> tuple[int, int]:
    """Compare canonicalized Linux, macOS, and Windows-shaped run metadata."""

    source = case.model_dump(mode="json")
    baseline = normalize_portable_data(source)
    baseline_bytes = canonical_json_bytes(baseline)
    mismatches = 0
    violations = len(portability_violations(baseline))
    roots = {
        "linux": "/tmp/intentforge/",
        "macos": "/private/tmp/intentforge/",
        "windows": "C:\\Users\\IntentForge\\AppData\\Local\\Temp\\intentforge\\",
    }
    for platform_name, root in roots.items():
        variant = json.loads(json.dumps(source))
        variant["request_id"] = f"{platform_name}_request"
        if variant.get("run_id") is not None:
            variant["run_id"] = f"{platform_name}_run"
        if variant.get("parent_run_id") is not None:
            variant["parent_run_id"] = f"{platform_name}_parent"
        variant["runtime_metadata"] = {
            "platform": platform_name,
            "timezone": "local",
            "temporary_directory": root,
        }
        for artifact in variant.get("artifact_records", []):
            relative = str(artifact.get("path", "")).replace("\\", "/")
            if platform_name == "windows":
                artifact["path"] = root + relative.replace("/", "\\")
            else:
                artifact["path"] = root + relative
            artifact["request_id"] = f"{platform_name}_request"
            if artifact.get("run_id") is not None:
                artifact["run_id"] = f"{platform_name}_run"
        normalized = normalize_portable_data(variant)
        mismatches += int(canonical_json_bytes(normalized) != baseline_bytes)
        violations += len(portability_violations(normalized))
    return mismatches, violations


def _review_policy_section(run_dir: Path, assurance_section: dict[str, Any]) -> dict[str, Any]:
    review_dir = run_dir / "review_policy"
    manifest_validation = validate_review_policy_manifest()
    policies = load_review_policies()
    policy_validation_pass_count = sum(validate_review_policy(policy).passed for policy in policies)
    shared_resources = collect_review_evaluation_resources()
    fixture_specs = {
        "wall_build": ("intentforge_standard_design_review_v1", "accepted_within_declared_scope"),
        "l_build": ("intentforge_standard_design_review_v1", "accepted_within_declared_scope"),
        "partial_feature": ("intentforge_standard_design_review_v1", "accepted_with_conditions"),
        "rejected": ("intentforge_safe_rejection_review_v1", "accepted_within_declared_scope"),
        "edit": ("intentforge_edit_review_v1", "accepted_within_declared_scope"),
    }
    decisions = []
    decision_validation_pass_count = 0
    audit_package_validation_pass_count = 0
    audit_package_hash_mismatch_count = 0
    deterministic_finding_mismatch_count = 0
    deterministic_condition_mismatch_count = 0
    deterministic_decision_mismatch_count = 0
    expected_decision_mismatch_count = 0
    policy_scope_mismatch_count = 0
    provenance_validation_pass_count = 0
    provenance_missing_count = 0
    provenance_snapshot_mismatch_count = 0
    provenance_execution_node_mismatch_count = 0
    provenance_replay_mismatch_count = 0
    provenance_evidence_matrix_mismatch_count = 0
    deterministic_provenance_mismatch_count = 0
    offline_verification_pass_count = 0
    offline_assurance_claim_count = 0
    offline_evidence_matrix_mismatch_count = 0
    offline_policy_catalog_mismatch_count = 0
    offline_static_replay_mismatch_count = 0
    offline_hash_mismatch_count = 0
    portability_violation_count = 0
    cross_platform_portability_mismatch_count = 0
    cas_object_hash_mismatch_count = 0
    aggregate = {
        "unknown_claim_reference_count": 0,
        "unknown_validation_reference_count": 0,
        "unknown_capability_reference_count": 0,
        "unknown_evidence_reference_count": 0,
        "unknown_rule_reference_count": 0,
    }
    fixture_results: dict[str, Any] = {}
    fixture_cases: dict[str, AssuranceCase] = {}
    fixture_decisions: dict[str, Any] = {}
    case_paths = assurance_section.get("fixture_case_paths", {})
    for fixture_name, (policy_id, expected_status) in fixture_specs.items():
        try:
            case = AssuranceCase.model_validate_json(Path(case_paths[fixture_name]).read_text(encoding="utf-8"))
            policy = get_review_policy(policy_id)
            first = evaluate_assurance_case(policy, case, resources=shared_resources)
            second = evaluate_assurance_case(policy, case, resources=shared_resources)
        except (KeyError, OSError, ValueError, ReviewEvaluationError) as exc:
            policy_scope_mismatch_count += int(isinstance(exc, ReviewEvaluationError))
            fixture_results[fixture_name] = {"passed": False, "error": str(exc)}
            continue
        deterministic_decision_mismatch_count += int(first.decision_id != second.decision_id)
        deterministic_provenance_mismatch_count += int(
            first.decision_provenance is None
            or second.decision_provenance is None
            or first.decision_provenance.provenance_id != second.decision_provenance.provenance_id
        )
        deterministic_finding_mismatch_count += int(
            [item.finding_id for item in first.findings] != [item.finding_id for item in second.findings]
        )
        deterministic_condition_mismatch_count += int(
            [item.condition_id for item in first.conditions] != [item.condition_id for item in second.conditions]
        )
        expected_decision_mismatch_count += int(first.decision_status != expected_status)
        validation = validate_review_decision(first, policy=policy, assurance_case=case)
        provenance_validation = verify_decision_provenance(first, perform_replay=True)
        provenance_validation_pass_count += int(provenance_validation.passed)
        provenance_missing_count += int(first.decision_provenance is None)
        provenance_snapshot_mismatch_count += provenance_validation.snapshot_mismatch_count
        provenance_execution_node_mismatch_count += provenance_validation.execution_node_mismatch_count
        provenance_replay_mismatch_count += provenance_validation.replay_mismatch_count
        provenance_evidence_matrix_mismatch_count += int(
            provenance_validation.evidence_definition_count != 65
            or provenance_validation.evidence_observation_count != 65
        )
        decision_validation_pass_count += int(validation.passed)
        for key in aggregate:
            aggregate[key] += int(validation.metrics.get(key, 0))
        package = build_audit_package(
            case,
            review_dir / "packages" / fixture_name,
            review_policy=policy,
            review_decision=first,
        )
        audit_package_validation_pass_count += int(package["validation"]["passed"])
        audit_package_hash_mismatch_count += int(package["validation"].get("hash_mismatch_count", 0))
        offline = verify_offline_audit_package(package["package_path"])
        offline_verification_pass_count += int(offline.passed)
        offline_assurance_claim_count += int(offline.metrics.get("assurance_claim_count", 0) or 0)
        offline_evidence_matrix_mismatch_count += int(
            offline.metrics.get("evidence_definition_count") != 65
            or offline.metrics.get("evidence_observation_count") != 65
        )
        offline_policy_catalog_mismatch_count += int(
            offline.metrics.get("policy_catalog_count") != 5
            or offline.metrics.get("policy_catalog_check_count") != 54
        )
        offline_static_replay_mismatch_count += int(
            offline.metrics.get("static_check_replay_mismatch_count", 0) or 0
        )
        offline_hash_mismatch_count += int(offline.metrics.get("hash_mismatch_count", 0) or 0)
        cas_object_hash_mismatch_count += int(offline.metrics.get("cas_object_hash_mismatch_count", 0) or 0)
        portability_violation_count += int(offline.metrics.get("portability_violation_count", 0) or 0)
        platform_mismatches, platform_violations = _cross_platform_portability_check(case)
        cross_platform_portability_mismatch_count += platform_mismatches
        portability_violation_count += platform_violations
        decision_path = review_dir / "decisions" / f"{fixture_name}.json"
        _write_json(first.model_dump(mode="json"), decision_path)
        fixture_results[fixture_name] = {
            "passed": validation.passed and provenance_validation.passed and offline.passed
                      and first.decision_status == expected_status and package["validation"]["passed"],
            "policy_id": policy_id,
            "decision_status": first.decision_status,
            "expected_status": expected_status,
            "decision_id": first.decision_id,
            "decision_path": str(decision_path),
            "package_id": package["package_id"],
            "provenance_id": None if first.decision_provenance is None else first.decision_provenance.provenance_id,
            "provenance_verified": provenance_validation.passed,
            "offline_verified": offline.passed,
            "offline_claim_count": offline.metrics.get("assurance_claim_count", 0),
        }
        decisions.append(first)
        fixture_cases[fixture_name] = case
        fixture_decisions[fixture_name] = first

    cas_store_failure_count = 0
    cas_deterministic_mismatch_count = 0
    predecessor_embedding_mismatch_count = 0
    chain_validation_pass_count = 0
    chain_length = 0
    chain_tamper_detection_pass_count = 0
    chain_pointer_mismatch_count = 0
    chain_missing_predecessor_count = 0
    chain_addresses: list[str] = []
    chain_errors: list[str] = []
    try:
        chain_store = review_dir / "cas_store"
        chain_specs = (
            ("wall_build", "intentforge_standard_design_review_v1"),
            ("partial_feature", "intentforge_standard_design_review_v1"),
            ("edit", "intentforge_edit_review_v1"),
        )
        predecessor = None
        head_storage_path = None
        for chain_index, (fixture_name, policy_id) in enumerate(chain_specs):
            chain_case = attach_assurance_predecessor(fixture_cases[fixture_name], predecessor)
            chain_policy = get_review_policy(policy_id)
            chain_decision = evaluate_assurance_case(
                chain_policy,
                chain_case,
                resources=shared_resources,
            )
            first_package = build_audit_package(
                chain_case,
                review_dir / "chain_packages" / f"{chain_index}_a",
                review_policy=chain_policy,
                review_decision=chain_decision,
                predecessor_hash_pointer=predecessor,
            )
            second_package = build_audit_package(
                chain_case,
                review_dir / "chain_packages" / f"{chain_index}_b",
                review_policy=chain_policy,
                review_decision=chain_decision,
                predecessor_hash_pointer=predecessor,
            )
            cas_deterministic_mismatch_count += int(
                first_package["package_id"] != second_package["package_id"]
            )
            stored = store_audit_package(first_package["package_path"], chain_store)
            reused = store_audit_package(first_package["package_path"], chain_store)
            cas_store_failure_count += int(not stored.passed or not reused.passed or not reused.reused_existing)
            if stored.content_address is None or stored.storage_path is None:
                raise ValueError("CAS store did not return a content address and storage path")
            embedded = (
                chain_case.predecessor_hash_pointer == predecessor
                and all(item.predecessor_hash_pointer == predecessor for item in chain_case.claims)
                and all(item.predecessor_hash_pointer == predecessor for item in chain_case.arguments)
                and chain_decision.predecessor_hash_pointer == predecessor
                and chain_decision.decision_provenance is not None
                and chain_decision.decision_provenance.predecessor_hash_pointer == predecessor
            )
            if predecessor is not None and chain_decision.decision_provenance is not None:
                embedded = embedded and any(
                    item.snapshot_type == "audit_lineage"
                    and item.payload.get("predecessor_hash_pointer") == predecessor
                    for item in chain_decision.decision_provenance.snapshots
                ) and any(
                    item.node_type == "lineage_binding"
                    for item in chain_decision.decision_provenance.execution_nodes
                )
            predecessor_embedding_mismatch_count += int(not embedded)
            predecessor = stored.content_address
            chain_addresses.append(stored.content_address)
            head_storage_path = stored.storage_path
        if head_storage_path is None:
            raise ValueError("CAS chain did not produce a head package")
        chain_result = verify_audit_chain(head_storage_path, store_root=chain_store)
        chain_validation_pass_count = int(chain_result.passed)
        chain_length = chain_result.chain_length
        chain_pointer_mismatch_count = chain_result.pointer_mismatch_count
        chain_missing_predecessor_count = chain_result.missing_predecessor_count
        chain_errors.extend(chain_result.errors)
        for scenario in ("modified", "missing", "switched"):
            scenario_store = review_dir / f"cas_tamper_{scenario}"
            shutil.copytree(chain_store, scenario_store)
            genesis_path = cas_storage_path(scenario_store, chain_addresses[0])
            if scenario == "modified":
                target = genesis_path / "assurance_case.json"
                target.write_bytes(target.read_bytes() + b" ")
            elif scenario == "missing":
                shutil.rmtree(genesis_path)
            else:
                switched_source = cas_storage_path(scenario_store, chain_addresses[1])
                switched_copy = review_dir / "switched_package_copy"
                if switched_copy.exists():
                    shutil.rmtree(switched_copy)
                shutil.copytree(switched_source, switched_copy)
                shutil.rmtree(genesis_path)
                shutil.copytree(switched_copy, genesis_path)
            scenario_head = cas_storage_path(scenario_store, chain_addresses[-1])
            tampered = verify_audit_chain(scenario_head, store_root=scenario_store)
            chain_tamper_detection_pass_count += int(not tampered.passed)
    except (OSError, ValueError, KeyError) as exc:
        cas_store_failure_count += 1
        chain_errors.append(str(exc))

    full_policy_incompatible_acceptance_count = 0
    try:
        standard_case = AssuranceCase.model_validate_json(Path(case_paths["wall_build"]).read_text(encoding="utf-8"))
        incompatible = evaluate_assurance_case(
            get_review_policy("intentforge_full_design_review_v1"),
            standard_case,
            resources=shared_resources,
        )
        full_policy_incompatible_acceptance_count = int(
            incompatible.decision_status in {"accepted_within_declared_scope", "accepted_with_conditions"}
        )
    except (KeyError, OSError, ValueError, ReviewEvaluationError):
        full_policy_incompatible_acceptance_count = 0

    semantic_diff_generation_failure_count = 0
    semantic_diff_deterministic_mismatch_count = 0
    multi_variant_diff_deterministic_mismatch_count = 0
    semantic_diff_count = 0
    try:
        baseline = next(item for item in decisions if item.cad_family == "wall_mounted_bracket" and item.decision_status == "accepted_within_declared_scope")
        partial = next(item for item in decisions if item.decision_status == "accepted_with_conditions")
        first_diff = diff_review_decisions(baseline, partial)
        second_diff = diff_review_decisions(baseline, partial)
        semantic_diff_count = 1
        semantic_diff_deterministic_mismatch_count = int(
            first_diff.diff_id != second_diff.diff_id or first_diff.content_id != second_diff.content_id
        )
        variants = [item for item in decisions if item.decision_id != baseline.decision_id][:3]
        first_multi = diff_review_variants(baseline, variants)
        second_multi = diff_review_variants(baseline, variants)
        multi_variant_diff_deterministic_mismatch_count = int(
            first_multi.audit_id != second_multi.audit_id or first_multi.content_id != second_multi.content_id
        )
        _write_json(first_diff.model_dump(mode="json"), review_dir / "review_semantic_diff.json")
        _write_json(first_multi.model_dump(mode="json"), review_dir / "review_multi_variant_diff.json")
    except (StopIteration, ValueError) as exc:
        semantic_diff_generation_failure_count = 1
        fixture_results["semantic_diff"] = {"passed": False, "error": str(exc)}

    finding_count = sum(len(item.findings) for item in decisions)
    result = {
        "review_policy_manifest_valid": manifest_validation.passed,
        "review_policy_count": len(policies),
        "review_policy_validation_pass_count": policy_validation_pass_count,
        "review_fixture_count": len(fixture_specs),
        "review_decision_count": len(decisions),
        "accepted_decision_count": sum(item.decision_status == "accepted_within_declared_scope" for item in decisions),
        "conditional_decision_count": sum(item.decision_status == "accepted_with_conditions" for item in decisions),
        "manual_review_decision_count": sum(item.decision_status == "manual_review_required" for item in decisions),
        "rejected_decision_count": sum(item.decision_status == "rejected_by_policy" for item in decisions),
        "unresolved_decision_count": sum(item.decision_status == "unresolved" for item in decisions),
        "total_policy_check_count": finding_count,
        "passed_policy_check_count": sum(item.passed_check_count for item in decisions),
        "failed_policy_check_count": sum(item.failed_check_count for item in decisions),
        "unresolved_policy_check_count": sum(item.unresolved_check_count for item in decisions),
        "not_applicable_policy_check_count": sum(item.not_applicable_check_count for item in decisions),
        "blocking_finding_count": sum(item.blocking_finding_count for item in decisions),
        "manual_review_finding_count": sum(item.manual_review_finding_count for item in decisions),
        "condition_count": sum(len(item.conditions) for item in decisions),
        **aggregate,
        "policy_scope_mismatch_count": policy_scope_mismatch_count,
        "unsafe_path_count": 0,
        "deterministic_finding_mismatch_count": deterministic_finding_mismatch_count,
        "deterministic_condition_mismatch_count": deterministic_condition_mismatch_count,
        "deterministic_decision_mismatch_count": deterministic_decision_mismatch_count,
        "review_decision_validation_pass_count": decision_validation_pass_count,
        "review_provenance_validation_pass_count": provenance_validation_pass_count,
        "review_provenance_missing_count": provenance_missing_count,
        "review_provenance_snapshot_mismatch_count": provenance_snapshot_mismatch_count,
        "review_provenance_execution_node_mismatch_count": provenance_execution_node_mismatch_count,
        "review_provenance_replay_mismatch_count": provenance_replay_mismatch_count,
        "review_provenance_evidence_matrix_mismatch_count": provenance_evidence_matrix_mismatch_count,
        "review_deterministic_provenance_mismatch_count": deterministic_provenance_mismatch_count,
        "review_semantic_diff_count": semantic_diff_count,
        "review_semantic_diff_generation_failure_count": semantic_diff_generation_failure_count,
        "review_semantic_diff_deterministic_mismatch_count": semantic_diff_deterministic_mismatch_count,
        "review_multi_variant_diff_deterministic_mismatch_count": multi_variant_diff_deterministic_mismatch_count,
        "review_offline_verification_pass_count": offline_verification_pass_count,
        "review_offline_assurance_claim_count": offline_assurance_claim_count,
        "review_offline_evidence_matrix_mismatch_count": offline_evidence_matrix_mismatch_count,
        "review_offline_policy_catalog_mismatch_count": offline_policy_catalog_mismatch_count,
        "review_offline_static_replay_mismatch_count": offline_static_replay_mismatch_count,
        "review_offline_hash_mismatch_count": offline_hash_mismatch_count,
        "review_portability_violation_count": portability_violation_count,
        "review_cross_platform_portability_mismatch_count": cross_platform_portability_mismatch_count,
        "review_cas_store_failure_count": cas_store_failure_count,
        "review_cas_object_hash_mismatch_count": cas_object_hash_mismatch_count,
        "review_cas_deterministic_mismatch_count": cas_deterministic_mismatch_count,
        "review_predecessor_embedding_mismatch_count": predecessor_embedding_mismatch_count,
        "review_chain_validation_pass_count": chain_validation_pass_count,
        "review_chain_length": chain_length,
        "review_chain_tamper_detection_pass_count": chain_tamper_detection_pass_count,
        "review_chain_pointer_mismatch_count": chain_pointer_mismatch_count,
        "review_chain_missing_predecessor_count": chain_missing_predecessor_count,
        "review_chain_addresses": chain_addresses,
        "review_chain_errors": chain_errors,
        "review_audit_package_validation_pass_count": audit_package_validation_pass_count,
        "review_audit_package_hash_mismatch_count": audit_package_hash_mismatch_count,
        "expected_decision_mismatch_count": expected_decision_mismatch_count,
        "full_policy_incompatible_acceptance_count": full_policy_incompatible_acceptance_count,
        "fixture_results": fixture_results,
        "policy_validation_errors": manifest_validation.errors,
    }
    result["passed"] = (
        manifest_validation.passed
        and policy_validation_pass_count == len(policies)
        and len(decisions) == len(fixture_specs)
        and decision_validation_pass_count == len(fixture_specs)
        and provenance_validation_pass_count == len(fixture_specs)
        and audit_package_validation_pass_count == len(fixture_specs)
        and not any(aggregate.values())
        and policy_scope_mismatch_count == 0
        and deterministic_finding_mismatch_count == 0
        and deterministic_condition_mismatch_count == 0
        and deterministic_decision_mismatch_count == 0
        and audit_package_hash_mismatch_count == 0
        and expected_decision_mismatch_count == 0
        and full_policy_incompatible_acceptance_count == 0
        and provenance_missing_count == 0
        and provenance_snapshot_mismatch_count == 0
        and provenance_execution_node_mismatch_count == 0
        and provenance_replay_mismatch_count == 0
        and provenance_evidence_matrix_mismatch_count == 0
        and deterministic_provenance_mismatch_count == 0
        and semantic_diff_generation_failure_count == 0
        and semantic_diff_deterministic_mismatch_count == 0
        and multi_variant_diff_deterministic_mismatch_count == 0
        and offline_verification_pass_count == len(fixture_specs)
        and offline_assurance_claim_count == 49
        and offline_evidence_matrix_mismatch_count == 0
        and offline_policy_catalog_mismatch_count == 0
        and offline_static_replay_mismatch_count == 0
        and offline_hash_mismatch_count == 0
        and portability_violation_count == 0
        and cross_platform_portability_mismatch_count == 0
        and cas_store_failure_count == 0
        and cas_object_hash_mismatch_count == 0
        and cas_deterministic_mismatch_count == 0
        and predecessor_embedding_mismatch_count == 0
        and chain_validation_pass_count == 1
        and chain_length == 3
        and chain_tamper_detection_pass_count == 3
        and chain_pointer_mismatch_count == 0
        and chain_missing_predecessor_count == 0
    )
    result["review_gate_passed"] = result["passed"]
    report_path = review_dir / "review_policy_harness_report.json"
    _write_json(result, report_path)
    result["report_path"] = str(report_path)
    return result


def _release_dossier_section(run_dir, review_policy_section):
    from intentforge.dossier import ReleaseDossierBuilder, verify_release_dossier, write_dossier
    from intentforge.redaction import default_redaction_config, export_redacted_package

    dossier_dir = run_dir / "release_dossier"
    chain_packages_dir = run_dir / "review_policy" / "chain_packages"
    chain_package_paths = []
    if chain_packages_dir.is_dir():
        chain_package_paths = sorted(p for p in chain_packages_dir.iterdir() if p.is_dir() and p.name.endswith("_a"))
    if len(chain_package_paths) < 2:
        return {"passed": False, "reason": "insufficient chain packages", "chain_package_count": len(chain_package_paths)}
    dossier_paths = [str(p) for p in chain_package_paths[:3]]
    builder = ReleaseDossierBuilder()
    dossier_validation_pass_count = 0
    dossier_hash_mismatch_count = 0
    merkle_root_count = 0
    rollup_status_counts = {}
    try:
        dossier = builder.build(dossier_paths)
        output_root = dossier_dir / "multi_component"
        write_dossier(dossier, output_root)
        result = verify_release_dossier(output_root)
        dossier_validation_pass_count = int(result.passed)
        dossier_hash_mismatch_count = int(not result.passed)
        merkle_root_count = 1
        rollup_status_counts[result.rollup_status or "unknown"] = rollup_status_counts.get(result.rollup_status or "unknown", 0) + 1
    except (ValueError, OSError, KeyError) as exc:
        return {"passed": False, "error": str(exc), "chain_package_count": len(chain_package_paths)}

    redacted_package_paths = []
    redacted_dir = dossier_dir / "redacted_packages"
    try:
        for source in chain_package_paths[:1]:
            redacted_dir.mkdir(parents=True, exist_ok=True)
            target = redacted_dir / source.name
            export_redacted_package(source_package=source, output_dir=target, config=default_redaction_config())
            if (target / "redacted_package_id.json").is_file() or (target / "redacted_cas_envelope.json").is_file():
                redacted_package_paths.append(target)
    except (OSError, ValueError):
        redacted_package_paths = []

    mixed_paths = dossier_paths + [str(p) for p in redacted_package_paths]
    mixed_validation_pass_count = 0
    mixed_merkle_root_count = 0
    if mixed_paths and mixed_paths != dossier_paths:
        try:
            mixed_dossier = builder.build(mixed_paths)
            mixed_output = dossier_dir / "mixed_redacted"
            write_dossier(mixed_dossier, mixed_output)
            mixed_result = verify_release_dossier(mixed_output)
            mixed_validation_pass_count = int(mixed_result.passed)
            mixed_merkle_root_count = 1
        except (ValueError, OSError, KeyError):
            mixed_validation_pass_count = 0

    tamper_envelope_detection_count = 0
    tamper_leaf_index_detection_count = 0
    tamper_child_detection_count = 0
    target_dossier_dir = dossier_dir / "multi_component"
    if target_dossier_dir.is_dir():
        envelope_path = target_dossier_dir / "dossier_envelope.json"
        leaf_index_path = target_dossier_dir / "dossier_leaf_index.json"
        if envelope_path.is_file():
            original = envelope_path.read_bytes()
            try:
                payload = json.loads(original)
                payload["root_hash"] = "sha256:" + "f" * 64
                envelope_path.write_text(json.dumps(payload), encoding="utf-8")
                tampered = verify_release_dossier(target_dossier_dir)
                if not tampered.passed:
                    tamper_envelope_detection_count = 1
            finally:
                envelope_path.write_bytes(original)
        if leaf_index_path.is_file():
            original = leaf_index_path.read_bytes()
            try:
                payload = json.loads(original)
                if payload:
                    payload[0]["content_address"] = "sha256:" + "1" * 64
                    leaf_index_path.write_text(json.dumps(payload), encoding="utf-8")
                    tampered = verify_release_dossier(target_dossier_dir)
                    if not tampered.passed:
                        tamper_leaf_index_detection_count = 1
            finally:
                leaf_index_path.write_bytes(original)
        child_target = Path(chain_package_paths[0]) / "review_decision.json"
        if child_target.is_file():
            original = child_target.read_bytes()
            try:
                payload = json.loads(original)
                payload["decision_status"] = "rejected_by_policy"
                child_target.write_text(json.dumps(payload), encoding="utf-8")
                tampered = verify_release_dossier(target_dossier_dir)
                if not tampered.passed:
                    tamper_child_detection_count = 1
            finally:
                child_target.write_bytes(original)

    result = {
        "passed": (dossier_validation_pass_count == 1 and dossier_hash_mismatch_count == 0
                   and merkle_root_count == 1 and tamper_envelope_detection_count == 1
                   and tamper_leaf_index_detection_count == 1 and tamper_child_detection_count == 1),
        "release_dossier_chain_package_count": len(chain_package_paths),
        "release_dossier_redacted_package_count": len(redacted_package_paths),
        "release_dossier_validation_pass_count": dossier_validation_pass_count,
        "release_dossier_hash_mismatch_count": dossier_hash_mismatch_count,
        "release_dossier_merkle_root_count": merkle_root_count,
        "release_dossier_rollup_status_counts": rollup_status_counts,
        "release_dossier_mixed_validation_pass_count": mixed_validation_pass_count,
        "release_dossier_mixed_merkle_root_count": mixed_merkle_root_count,
        "release_dossier_tamper_envelope_detection_count": tamper_envelope_detection_count,
        "release_dossier_tamper_leaf_index_detection_count": tamper_leaf_index_detection_count,
        "release_dossier_tamper_child_detection_count": tamper_child_detection_count,
        "release_dossier_output_path": str(dossier_dir / "multi_component"),
    }
    result["release_dossier_gate_passed"] = result["passed"]
    report_path = dossier_dir / "release_dossier_harness_report.json"
    _write_json(result, report_path)
    result["report_path"] = str(report_path)
    return result


def _demo_section(output_root: Path) -> dict[str, Any]:
    from intentforge.demo_runner import run_demo

    result = run_demo(output_root)
    failed_steps = [
        step
        for step in result["steps"]
        if not step["ok"] and not step.get("intentional_rejection", False)
    ]
    return {
        "passed": result["benchmark"]["failed"] == 0 and not failed_steps,
        "run_id": result["run_id"],
        "benchmark": result["benchmark"],
        "failed_step_count": len(failed_steps),
        "demo_report_path": result["demo_report_path"],
        "demo_summary_path": result["demo_summary_path"],
        "persistent_output_dir": result["output_dir"],
    }


def _section_error_count(section: dict[str, Any]) -> int:
    return 1 if section.get("error_type") else 0


def _failure_type_count(section: dict[str, Any], failure_type: str) -> int:
    failure_types = section.get("failure_types")
    if not isinstance(failure_types, dict):
        return 0
    return int(failure_types.get(failure_type, 0) or 0)


def _build_metrics(sections: dict[str, dict[str, Any]]) -> dict[str, float | int]:
    benchmark = sections.get("benchmark", {})
    sweep = sections.get("sweep", {})
    edit = sections.get("edit_preservation", {})
    adversarial = sections.get("adversarial_rejection", {})
    volume = sections.get("volume_delta", {})
    shape = sections.get("shape_inspection", {})
    feature_recognition = sections.get("feature_recognition", {})
    reasoning = sections.get("engineering_reasoning", {})
    rule_packs = sections.get("rule_packs", {})
    capability_coverage = sections.get("capability_coverage", {})
    evidence_trust = sections.get("evidence_trust", {})
    assurance = sections.get("assurance", {})
    review_policy = sections.get("review_policy", {})
    demo = sections.get("demo", {})

    unexpected_failure_count = int(benchmark.get("failed_cases", 0) or 0)
    unexpected_failure_count += int(sweep.get("failed_cases", 0) or 0)
    unexpected_failure_count += int(edit.get("failed_steps", 0) or 0)
    unexpected_failure_count += int(adversarial.get("failed_cases", 0) or 0)
    unexpected_failure_count += len(volume.get("failed_families", []) or [])
    unexpected_failure_count += len(shape.get("failed_families", []) or [])
    unexpected_failure_count += len(reasoning.get("failed_families", []) or [])
    unexpected_failure_count += int(rule_packs.get("invalid_pack_count", 0) or 0)
    unexpected_failure_count += 0 if rule_packs.get("legacy_compatibility_passed", True) else 1
    unexpected_failure_count += 0 if capability_coverage.get("passed", True) else 1
    unexpected_failure_count += 0 if evidence_trust.get("passed", True) else 1
    unexpected_failure_count += 0 if assurance.get("passed", True) else 1
    unexpected_failure_count += 0 if review_policy.get("passed", True) else 1
    unexpected_failure_count += int(demo.get("failed_step_count", 0) or 0)
    unexpected_failure_count += sum(_section_error_count(section) for section in sections.values())

    unsafe_acceptance_count = _failure_type_count(adversarial, "unexpected_acceptance")
    unsafe_acceptance_count += _failure_type_count(edit, "unexpected_acceptance")

    unexpected_exception_count = sum(
        _failure_type_count(section, "unexpected_exception") for section in sections.values()
    )
    unexpected_exception_count += sum(_section_error_count(section) for section in sections.values())

    return {
        "benchmark_pass_rate": float(benchmark.get("pass_rate", 0.0) or 0.0),
        "sweep_pass_rate": float(sweep.get("pass_rate", 0.0) or 0.0),
        "edit_preservation_rate": float(edit.get("edit_preservation_rate", 0.0) or 0.0),
        "adversarial_rejection_success_rate": float(adversarial.get("rejection_success_rate", 0.0) or 0.0),
        "feature_recognition_pass_rate": float(feature_recognition.get("pass_rate", 0.0) or 0.0),
        "feature_recognition_warning_count": int(feature_recognition.get("warning_count", 0) or 0),
        "reasoning_generation_pass_rate": float(reasoning.get("pass_rate", 0.0) or 0.0),
        "unknown_rule_reference_count": int(reasoning.get("unknown_rule_reference_count", 0) or 0),
        "duplicate_recommendation_count": int(reasoning.get("duplicate_recommendation_count", 0) or 0),
        "missing_limitation_count": int(reasoning.get("missing_limitation_count", 0) or 0),
        "recommendation_contradiction_count": int(reasoning.get("recommendation_contradiction_count", 0) or 0),
        "recommendation_applicability_error_count": int(reasoning.get("recommendation_applicability_error_count", 0) or 0),
        "nondeterministic_reasoning_report_count": int(reasoning.get("nondeterministic_reasoning_report_count", 0) or 0),
        "reasoning_report_id_mismatch_count": int(reasoning.get("reasoning_report_id_mismatch_count", 0) or 0),
        "rule_pack_load_pass_rate": 1.0 if rule_packs.get("passed", False) else 0.0,
        "active_pack_count": int(rule_packs.get("active_pack_count", 0) or 0),
        "active_rule_count": int(rule_packs.get("active_rule_count", 0) or 0),
        "duplicate_pack_id_count": int(rule_packs.get("duplicate_pack_id_count", 0) or 0),
        "duplicate_rule_id_count": int(rule_packs.get("duplicate_rule_id_count", 0) or 0),
        "invalid_pack_count": int(rule_packs.get("invalid_pack_count", 0) or 0),
        "rule_pack_unknown_rule_reference_count": int(rule_packs.get("unknown_rule_reference_count", 0) or 0),
        "legacy_compatibility_passed": 1 if rule_packs.get("legacy_compatibility_passed", False) else 0,
        "rule_pack_reasoning_regression_pass_rate": float(rule_packs.get("reasoning_regression_pass_rate", 0.0) or 0.0),
        "capability_manifest_valid": 1 if capability_coverage.get("capability_manifest_valid", False) else 0,
        "capability_count": int(capability_coverage.get("capability_count", 0) or 0),
        "supported_capability_count": int(capability_coverage.get("supported_capability_count", 0) or 0),
        "partial_capability_count": int(capability_coverage.get("partial_capability_count", 0) or 0),
        "unsupported_capability_count": int(capability_coverage.get("unsupported_capability_count", 0) or 0),
        "capability_active_rule_count": int(capability_coverage.get("active_rule_count", 0) or 0),
        "capability_mapped_rule_count": int(capability_coverage.get("mapped_rule_count", 0) or 0),
        "capability_orphan_rule_count": int(capability_coverage.get("orphan_rule_count", 0) or 0),
        "capability_unknown_reference_count": int(capability_coverage.get("unknown_reference_count", 0) or 0),
        "capability_duplicate_id_count": int(capability_coverage.get("duplicate_capability_id_count", 0) or 0),
        "capability_supported_missing_implementation_count": int(capability_coverage.get("supported_missing_implementation_count", 0) or 0),
        "capability_supported_missing_verification_count": int(capability_coverage.get("supported_missing_verification_count", 0) or 0),
        "capability_partial_missing_limitation_count": int(capability_coverage.get("partial_missing_limitation_count", 0) or 0),
        "capability_unsupported_missing_boundary_count": int(capability_coverage.get("unsupported_missing_boundary_count", 0) or 0),
        "capability_implementation_evidence_completeness": float(capability_coverage.get("implementation_evidence_completeness", 0.0) or 0.0),
        "capability_verification_evidence_completeness": float(capability_coverage.get("verification_evidence_completeness", 0.0) or 0.0),
        "capability_nondeterministic_report_count": int(capability_coverage.get("nondeterministic_report_count", 0) or 0),
        "evidence_manifest_valid": 1 if evidence_trust.get("evidence_manifest_valid", False) else 0,
        "evidence_definition_count": int(evidence_trust.get("evidence_definition_count", 0) or 0),
        "evidence_required_count": int(evidence_trust.get("required_evidence_count", 0) or 0),
        "evidence_verified_count": int(evidence_trust.get("verified_evidence_count", 0) or 0),
        "evidence_failed_count": int(evidence_trust.get("failed_evidence_count", 0) or 0),
        "evidence_unresolved_count": int(evidence_trust.get("unresolved_evidence_count", 0) or 0),
        "evidence_unavailable_count": int(evidence_trust.get("unavailable_evidence_count", 0) or 0),
        "evidence_stale_count": int(evidence_trust.get("stale_evidence_count", 0) or 0),
        "evidence_orphan_count": int(evidence_trust.get("orphan_evidence_count", 0) or 0),
        "evidence_duplicate_id_count": int(evidence_trust.get("duplicate_evidence_id_count", 0) or 0),
        "evidence_duplicate_reference_count": int(evidence_trust.get("duplicate_reference_count", 0) or 0),
        "evidence_family_mismatch_count": int(evidence_trust.get("family_mismatch_count", 0) or 0),
        "evidence_stage_mismatch_count": int(evidence_trust.get("stage_mismatch_count", 0) or 0),
        "evidence_unknown_capability_reference_count": int(evidence_trust.get("unknown_capability_reference_count", 0) or 0),
        "evidence_unknown_rule_reference_count": int(evidence_trust.get("unknown_rule_reference_count", 0) or 0),
        "evidence_unknown_pack_reference_count": int(evidence_trust.get("unknown_pack_reference_count", 0) or 0),
        "evidence_unsafe_file_reference_count": int(evidence_trust.get("unsafe_file_reference_count", 0) or 0),
        "evidence_supported_missing_implementation_count": int(evidence_trust.get("supported_missing_implementation_count", 0) or 0),
        "evidence_supported_missing_verification_count": int(evidence_trust.get("supported_missing_verification_count", 0) or 0),
        "evidence_partial_missing_limitation_count": int(evidence_trust.get("partial_missing_limitation_count", 0) or 0),
        "evidence_unsupported_missing_boundary_count": int(evidence_trust.get("unsupported_missing_boundary_count", 0) or 0),
        "evidence_deterministic_bundle_mismatch_count": int(evidence_trust.get("deterministic_bundle_mismatch_count", 0) or 0),
        "evidence_deterministic_trust_report_mismatch_count": int(evidence_trust.get("deterministic_report_mismatch_count", 0) or 0),
        "assurance_gate_passed": 1 if assurance.get("assurance_gate_passed", False) else 0,
        "assurance_fixture_count": int(assurance.get("assurance_fixture_count", 0) or 0),
        "assurance_case_count": int(assurance.get("assurance_case_count", 0) or 0),
        "assurance_claim_count": int(assurance.get("assurance_claim_count", 0) or 0),
        "assurance_invalid_capability_reference_count": int(assurance.get("invalid_capability_reference_count", 0) or 0),
        "assurance_invalid_evidence_reference_count": int(assurance.get("invalid_evidence_reference_count", 0) or 0),
        "assurance_invalid_rule_reference_count": int(assurance.get("invalid_rule_reference_count", 0) or 0),
        "assurance_unsafe_artifact_path_count": int(assurance.get("unsafe_artifact_path_count", 0) or 0),
        "assurance_missing_required_validation_count": int(assurance.get("missing_required_validation_count", 0) or 0),
        "assurance_deterministic_case_mismatch_count": int(assurance.get("deterministic_assurance_case_mismatch_count", 0) or 0),
        "assurance_deterministic_package_mismatch_count": int(assurance.get("deterministic_audit_package_mismatch_count", 0) or 0),
        "assurance_package_hash_mismatch_count": int(assurance.get("audit_package_hash_mismatch_count", 0) or 0),
        "review_gate_passed": 1 if review_policy.get("review_gate_passed", False) else 0,
        "review_policy_manifest_valid": 1 if review_policy.get("review_policy_manifest_valid", False) else 0,
        "review_policy_count": int(review_policy.get("review_policy_count", 0) or 0),
        "review_invalid_policy_count": max(0, int(review_policy.get("review_policy_count", 0) or 0) - int(review_policy.get("review_policy_validation_pass_count", 0) or 0)),
        "review_fixture_count": int(review_policy.get("review_fixture_count", 0) or 0),
        "review_decision_count": int(review_policy.get("review_decision_count", 0) or 0),
        "review_accepted_decision_count": int(review_policy.get("accepted_decision_count", 0) or 0),
        "review_conditional_decision_count": int(review_policy.get("conditional_decision_count", 0) or 0),
        "review_manual_review_decision_count": int(review_policy.get("manual_review_decision_count", 0) or 0),
        "review_rejected_decision_count": int(review_policy.get("rejected_decision_count", 0) or 0),
        "review_unresolved_decision_count": int(review_policy.get("unresolved_decision_count", 0) or 0),
        "review_unknown_claim_reference_count": int(review_policy.get("unknown_claim_reference_count", 0) or 0),
        "review_unknown_validation_reference_count": int(review_policy.get("unknown_validation_reference_count", 0) or 0),
        "review_unknown_capability_reference_count": int(review_policy.get("unknown_capability_reference_count", 0) or 0),
        "review_unknown_evidence_reference_count": int(review_policy.get("unknown_evidence_reference_count", 0) or 0),
        "review_unknown_rule_reference_count": int(review_policy.get("unknown_rule_reference_count", 0) or 0),
        "review_policy_scope_mismatch_count": int(review_policy.get("policy_scope_mismatch_count", 0) or 0),
        "review_unsafe_path_count": int(review_policy.get("unsafe_path_count", 0) or 0),
        "review_deterministic_finding_mismatch_count": int(review_policy.get("deterministic_finding_mismatch_count", 0) or 0),
        "review_deterministic_condition_mismatch_count": int(review_policy.get("deterministic_condition_mismatch_count", 0) or 0),
        "review_deterministic_decision_mismatch_count": int(review_policy.get("deterministic_decision_mismatch_count", 0) or 0),
        "review_audit_package_hash_mismatch_count": int(review_policy.get("review_audit_package_hash_mismatch_count", 0) or 0),
        "review_expected_decision_mismatch_count": int(review_policy.get("expected_decision_mismatch_count", 0) or 0),
        "review_full_policy_incompatible_acceptance_count": int(review_policy.get("full_policy_incompatible_acceptance_count", 0) or 0),
        "review_provenance_validation_pass_count": int(review_policy.get("review_provenance_validation_pass_count", 0) or 0),
        "review_provenance_missing_count": int(review_policy.get("review_provenance_missing_count", 0) or 0),
        "review_provenance_snapshot_mismatch_count": int(review_policy.get("review_provenance_snapshot_mismatch_count", 0) or 0),
        "review_provenance_execution_node_mismatch_count": int(review_policy.get("review_provenance_execution_node_mismatch_count", 0) or 0),
        "review_provenance_replay_mismatch_count": int(review_policy.get("review_provenance_replay_mismatch_count", 0) or 0),
        "review_provenance_evidence_matrix_mismatch_count": int(review_policy.get("review_provenance_evidence_matrix_mismatch_count", 0) or 0),
        "review_deterministic_provenance_mismatch_count": int(review_policy.get("review_deterministic_provenance_mismatch_count", 0) or 0),
        "review_semantic_diff_count": int(review_policy.get("review_semantic_diff_count", 0) or 0),
        "review_semantic_diff_generation_failure_count": int(review_policy.get("review_semantic_diff_generation_failure_count", 0) or 0),
        "review_semantic_diff_deterministic_mismatch_count": int(review_policy.get("review_semantic_diff_deterministic_mismatch_count", 0) or 0),
        "review_multi_variant_diff_deterministic_mismatch_count": int(review_policy.get("review_multi_variant_diff_deterministic_mismatch_count", 0) or 0),
        "review_offline_verification_pass_count": int(review_policy.get("review_offline_verification_pass_count", 0) or 0),
        "review_offline_assurance_claim_count": int(review_policy.get("review_offline_assurance_claim_count", 0) or 0),
        "review_offline_evidence_matrix_mismatch_count": int(review_policy.get("review_offline_evidence_matrix_mismatch_count", 0) or 0),
        "review_offline_policy_catalog_mismatch_count": int(review_policy.get("review_offline_policy_catalog_mismatch_count", 0) or 0),
        "review_offline_static_replay_mismatch_count": int(review_policy.get("review_offline_static_replay_mismatch_count", 0) or 0),
        "review_offline_hash_mismatch_count": int(review_policy.get("review_offline_hash_mismatch_count", 0) or 0),
        "review_portability_violation_count": int(review_policy.get("review_portability_violation_count", 0) or 0),
        "review_cross_platform_portability_mismatch_count": int(review_policy.get("review_cross_platform_portability_mismatch_count", 0) or 0),
        "review_cas_store_failure_count": int(review_policy.get("review_cas_store_failure_count", 0) or 0),
        "review_cas_object_hash_mismatch_count": int(review_policy.get("review_cas_object_hash_mismatch_count", 0) or 0),
        "review_cas_deterministic_mismatch_count": int(review_policy.get("review_cas_deterministic_mismatch_count", 0) or 0),
        "review_predecessor_embedding_mismatch_count": int(review_policy.get("review_predecessor_embedding_mismatch_count", 0) or 0),
        "review_chain_validation_pass_count": int(review_policy.get("review_chain_validation_pass_count", 0) or 0),
        "review_chain_length": int(review_policy.get("review_chain_length", 0) or 0),
        "review_chain_tamper_detection_pass_count": int(review_policy.get("review_chain_tamper_detection_pass_count", 0) or 0),
        "review_chain_pointer_mismatch_count": int(review_policy.get("review_chain_pointer_mismatch_count", 0) or 0),
        "review_chain_missing_predecessor_count": int(review_policy.get("review_chain_missing_predecessor_count", 0) or 0),
        "unexpected_failure_count": unexpected_failure_count,
        "unsafe_acceptance_count": unsafe_acceptance_count,
        "unexpected_exception_count": unexpected_exception_count,
    }


def compute_quality_gates(report: dict[str, Any]) -> dict[str, Any]:
    """Compute quality gate results for a technical harness report."""

    metrics = report.get("metrics", {})
    gates = dict(report.get("quality_gates") or QUALITY_GATES)
    failed_gates: list[dict[str, Any]] = []

    gate_specs = (
        ("benchmark_pass_rate_min", "benchmark_pass_rate", ">="),
        ("sweep_pass_rate_min", "sweep_pass_rate", ">="),
        ("edit_preservation_rate_min", "edit_preservation_rate", ">="),
        ("adversarial_rejection_success_rate_min", "adversarial_rejection_success_rate", ">="),
        ("reasoning_generation_pass_rate_min", "reasoning_generation_pass_rate", ">="),
        ("unexpected_failure_count_max", "unexpected_failure_count", "<="),
        ("unsafe_acceptance_count_max", "unsafe_acceptance_count", "<="),
        ("unexpected_exception_count_max", "unexpected_exception_count", "<="),
        ("unknown_rule_reference_count_max", "unknown_rule_reference_count", "<="),
        ("duplicate_recommendation_count_max", "duplicate_recommendation_count", "<="),
        ("missing_limitation_count_max", "missing_limitation_count", "<="),
        ("recommendation_contradiction_count_max", "recommendation_contradiction_count", "<="),
        ("recommendation_applicability_error_count_max", "recommendation_applicability_error_count", "<="),
        ("nondeterministic_reasoning_report_count_max", "nondeterministic_reasoning_report_count", "<="),
        ("reasoning_report_id_mismatch_count_max", "reasoning_report_id_mismatch_count", "<="),
        ("rule_pack_load_pass_rate_min", "rule_pack_load_pass_rate", ">="),
        ("active_pack_count_min", "active_pack_count", ">="),
        ("active_pack_count_max", "active_pack_count", "<="),
        ("active_rule_count_min", "active_rule_count", ">="),
        ("active_rule_count_max", "active_rule_count", "<="),
        ("duplicate_pack_id_count_max", "duplicate_pack_id_count", "<="),
        ("duplicate_rule_id_count_max", "duplicate_rule_id_count", "<="),
        ("invalid_pack_count_max", "invalid_pack_count", "<="),
        ("rule_pack_unknown_rule_reference_count_max", "rule_pack_unknown_rule_reference_count", "<="),
        ("legacy_compatibility_passed_min", "legacy_compatibility_passed", ">="),
        ("rule_pack_reasoning_regression_pass_rate_min", "rule_pack_reasoning_regression_pass_rate", ">="),
        ("capability_manifest_valid_min", "capability_manifest_valid", ">="),
        ("capability_duplicate_id_count_max", "capability_duplicate_id_count", "<="),
        ("capability_unknown_reference_count_max", "capability_unknown_reference_count", "<="),
        ("capability_supported_missing_implementation_count_max", "capability_supported_missing_implementation_count", "<="),
        ("capability_supported_missing_verification_count_max", "capability_supported_missing_verification_count", "<="),
        ("capability_partial_missing_limitation_count_max", "capability_partial_missing_limitation_count", "<="),
        ("capability_unsupported_missing_boundary_count_max", "capability_unsupported_missing_boundary_count", "<="),
        ("capability_orphan_rule_count_max", "capability_orphan_rule_count", "<="),
        ("capability_nondeterministic_report_count_max", "capability_nondeterministic_report_count", "<="),
        ("evidence_manifest_valid_min", "evidence_manifest_valid", ">="),
        ("evidence_duplicate_id_count_max", "evidence_duplicate_id_count", "<="),
        ("evidence_unknown_capability_reference_count_max", "evidence_unknown_capability_reference_count", "<="),
        ("evidence_unknown_rule_reference_count_max", "evidence_unknown_rule_reference_count", "<="),
        ("evidence_unknown_pack_reference_count_max", "evidence_unknown_pack_reference_count", "<="),
        ("evidence_unsafe_file_reference_count_max", "evidence_unsafe_file_reference_count", "<="),
        ("evidence_family_mismatch_count_max", "evidence_family_mismatch_count", "<="),
        ("evidence_stage_mismatch_count_max", "evidence_stage_mismatch_count", "<="),
        ("evidence_supported_missing_implementation_count_max", "evidence_supported_missing_implementation_count", "<="),
        ("evidence_supported_missing_verification_count_max", "evidence_supported_missing_verification_count", "<="),
        ("evidence_partial_missing_limitation_count_max", "evidence_partial_missing_limitation_count", "<="),
        ("evidence_unsupported_missing_boundary_count_max", "evidence_unsupported_missing_boundary_count", "<="),
        ("evidence_orphan_count_max", "evidence_orphan_count", "<="),
        ("evidence_deterministic_bundle_mismatch_count_max", "evidence_deterministic_bundle_mismatch_count", "<="),
        ("evidence_deterministic_trust_report_mismatch_count_max", "evidence_deterministic_trust_report_mismatch_count", "<="),
        ("assurance_gate_passed_min", "assurance_gate_passed", ">="),
        ("assurance_invalid_capability_reference_count_max", "assurance_invalid_capability_reference_count", "<="),
        ("assurance_invalid_evidence_reference_count_max", "assurance_invalid_evidence_reference_count", "<="),
        ("assurance_invalid_rule_reference_count_max", "assurance_invalid_rule_reference_count", "<="),
        ("assurance_unsafe_artifact_path_count_max", "assurance_unsafe_artifact_path_count", "<="),
        ("assurance_missing_required_validation_count_max", "assurance_missing_required_validation_count", "<="),
        ("assurance_deterministic_case_mismatch_count_max", "assurance_deterministic_case_mismatch_count", "<="),
        ("assurance_deterministic_package_mismatch_count_max", "assurance_deterministic_package_mismatch_count", "<="),
        ("assurance_package_hash_mismatch_count_max", "assurance_package_hash_mismatch_count", "<="),
        ("review_gate_passed_min", "review_gate_passed", ">="),
        ("review_policy_manifest_valid_min", "review_policy_manifest_valid", ">="),
        ("review_invalid_policy_count_max", "review_invalid_policy_count", "<="),
        ("review_unknown_claim_reference_count_max", "review_unknown_claim_reference_count", "<="),
        ("review_unknown_validation_reference_count_max", "review_unknown_validation_reference_count", "<="),
        ("review_unknown_capability_reference_count_max", "review_unknown_capability_reference_count", "<="),
        ("review_unknown_evidence_reference_count_max", "review_unknown_evidence_reference_count", "<="),
        ("review_unknown_rule_reference_count_max", "review_unknown_rule_reference_count", "<="),
        ("review_policy_scope_mismatch_count_max", "review_policy_scope_mismatch_count", "<="),
        ("review_unsafe_path_count_max", "review_unsafe_path_count", "<="),
        ("review_deterministic_finding_mismatch_count_max", "review_deterministic_finding_mismatch_count", "<="),
        ("review_deterministic_condition_mismatch_count_max", "review_deterministic_condition_mismatch_count", "<="),
        ("review_deterministic_decision_mismatch_count_max", "review_deterministic_decision_mismatch_count", "<="),
        ("review_audit_package_hash_mismatch_count_max", "review_audit_package_hash_mismatch_count", "<="),
        ("review_expected_decision_mismatch_count_max", "review_expected_decision_mismatch_count", "<="),
        ("review_full_policy_incompatible_acceptance_count_max", "review_full_policy_incompatible_acceptance_count", "<="),
        ("review_provenance_missing_count_max", "review_provenance_missing_count", "<="),
        ("review_provenance_snapshot_mismatch_count_max", "review_provenance_snapshot_mismatch_count", "<="),
        ("review_provenance_execution_node_mismatch_count_max", "review_provenance_execution_node_mismatch_count", "<="),
        ("review_provenance_replay_mismatch_count_max", "review_provenance_replay_mismatch_count", "<="),
        ("review_provenance_evidence_matrix_mismatch_count_max", "review_provenance_evidence_matrix_mismatch_count", "<="),
        ("review_deterministic_provenance_mismatch_count_max", "review_deterministic_provenance_mismatch_count", "<="),
        ("review_semantic_diff_generation_failure_count_max", "review_semantic_diff_generation_failure_count", "<="),
        ("review_semantic_diff_deterministic_mismatch_count_max", "review_semantic_diff_deterministic_mismatch_count", "<="),
        ("review_multi_variant_diff_deterministic_mismatch_count_max", "review_multi_variant_diff_deterministic_mismatch_count", "<="),
        ("review_offline_verification_pass_count_min", "review_offline_verification_pass_count", ">="),
        ("review_offline_assurance_claim_count_min", "review_offline_assurance_claim_count", ">="),
        ("review_offline_assurance_claim_count_max", "review_offline_assurance_claim_count", "<="),
        ("review_offline_evidence_matrix_mismatch_count_max", "review_offline_evidence_matrix_mismatch_count", "<="),
        ("review_offline_policy_catalog_mismatch_count_max", "review_offline_policy_catalog_mismatch_count", "<="),
        ("review_offline_static_replay_mismatch_count_max", "review_offline_static_replay_mismatch_count", "<="),
        ("review_offline_hash_mismatch_count_max", "review_offline_hash_mismatch_count", "<="),
        ("review_portability_violation_count_max", "review_portability_violation_count", "<="),
        ("review_cross_platform_portability_mismatch_count_max", "review_cross_platform_portability_mismatch_count", "<="),
        ("review_cas_store_failure_count_max", "review_cas_store_failure_count", "<="),
        ("review_cas_object_hash_mismatch_count_max", "review_cas_object_hash_mismatch_count", "<="),
        ("review_cas_deterministic_mismatch_count_max", "review_cas_deterministic_mismatch_count", "<="),
        ("review_predecessor_embedding_mismatch_count_max", "review_predecessor_embedding_mismatch_count", "<="),
        ("review_chain_validation_pass_count_min", "review_chain_validation_pass_count", ">="),
        ("review_chain_length_min", "review_chain_length", ">="),
        ("review_chain_tamper_detection_pass_count_min", "review_chain_tamper_detection_pass_count", ">="),
        ("review_chain_pointer_mismatch_count_max", "review_chain_pointer_mismatch_count", "<="),
        ("review_chain_missing_predecessor_count_max", "review_chain_missing_predecessor_count", "<="),
    )
    for gate_name, metric_name, operator in gate_specs:
        if gate_name not in gates or metric_name not in metrics:
            continue
        expected = gates[gate_name]
        actual = metrics.get(metric_name, 0)
        failed = actual < expected if operator == ">=" else actual > expected
        if failed:
            failed_gates.append(
                {
                    "gate": gate_name,
                    "metric": metric_name,
                    "expected": expected,
                    "actual": actual,
                    "operator": operator,
                }
            )

    return {
        "quality_gates": gates,
        "failed_gates": failed_gates,
        "quality_gates_passed": not failed_gates,
    }


def _build_summary(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        f"Technical harness run: {report['run_id']}",
        f"Overall passed: {str(report['overall_passed']).lower()}",
        f"Quality gates passed: {str(report['quality_gates_passed']).lower()}",
        "Metrics:",
        f"  - benchmark_pass_rate: {metrics['benchmark_pass_rate']:.4f}",
        f"  - sweep_pass_rate: {metrics['sweep_pass_rate']:.4f}",
        f"  - edit_preservation_rate: {metrics['edit_preservation_rate']:.4f}",
        f"  - adversarial_rejection_success_rate: {metrics['adversarial_rejection_success_rate']:.4f}",
        f"  - feature_recognition_pass_rate: {float(metrics.get('feature_recognition_pass_rate', 0.0)):.4f}",
        f"  - feature_recognition_warning_count: {int(metrics.get('feature_recognition_warning_count', 0))}",
        f"  - reasoning_generation_pass_rate: {float(metrics.get('reasoning_generation_pass_rate', 0.0)):.4f}",
        f"  - unknown_rule_reference_count: {int(metrics.get('unknown_rule_reference_count', 0))}",
        f"  - duplicate_recommendation_count: {int(metrics.get('duplicate_recommendation_count', 0))}",
        f"  - missing_limitation_count: {int(metrics.get('missing_limitation_count', 0))}",
        f"  - recommendation_contradiction_count: {int(metrics.get('recommendation_contradiction_count', 0))}",
        f"  - recommendation_applicability_error_count: {int(metrics.get('recommendation_applicability_error_count', 0))}",
        f"  - nondeterministic_reasoning_report_count: {int(metrics.get('nondeterministic_reasoning_report_count', 0))}",
        f"  - reasoning_report_id_mismatch_count: {int(metrics.get('reasoning_report_id_mismatch_count', 0))}",
        f"  - rule_pack_load_pass_rate: {float(metrics.get('rule_pack_load_pass_rate', 0.0)):.4f}",
        f"  - active_pack_count: {int(metrics.get('active_pack_count', 0))}",
        f"  - active_rule_count: {int(metrics.get('active_rule_count', 0))}",
        f"  - duplicate_pack_id_count: {int(metrics.get('duplicate_pack_id_count', 0))}",
        f"  - duplicate_rule_id_count: {int(metrics.get('duplicate_rule_id_count', 0))}",
        f"  - invalid_pack_count: {int(metrics.get('invalid_pack_count', 0))}",
        f"  - rule_pack_unknown_rule_reference_count: {int(metrics.get('rule_pack_unknown_rule_reference_count', 0))}",
        f"  - legacy_compatibility_passed: {int(metrics.get('legacy_compatibility_passed', 0))}",
        f"  - rule_pack_reasoning_regression_pass_rate: {float(metrics.get('rule_pack_reasoning_regression_pass_rate', 0.0)):.4f}",
        f"  - capability_manifest_valid: {int(metrics.get('capability_manifest_valid', 0))}",
        f"  - capability_count: {int(metrics.get('capability_count', 0))}",
        f"  - supported_capability_count: {int(metrics.get('supported_capability_count', 0))}",
        f"  - partial_capability_count: {int(metrics.get('partial_capability_count', 0))}",
        f"  - unsupported_capability_count: {int(metrics.get('unsupported_capability_count', 0))}",
        f"  - capability_mapped_rule_count: {int(metrics.get('capability_mapped_rule_count', 0))}",
        f"  - capability_orphan_rule_count: {int(metrics.get('capability_orphan_rule_count', 0))}",
        f"  - capability_unknown_reference_count: {int(metrics.get('capability_unknown_reference_count', 0))}",
        f"  - capability_implementation_evidence_completeness: {float(metrics.get('capability_implementation_evidence_completeness', 0.0)):.4f}",
        f"  - capability_verification_evidence_completeness: {float(metrics.get('capability_verification_evidence_completeness', 0.0)):.4f}",
        f"  - capability_nondeterministic_report_count: {int(metrics.get('capability_nondeterministic_report_count', 0))}",
        f"  - evidence_manifest_valid: {int(metrics.get('evidence_manifest_valid', 0))}",
        f"  - evidence_definition_count: {int(metrics.get('evidence_definition_count', 0))}",
        f"  - evidence_required_count: {int(metrics.get('evidence_required_count', 0))}",
        f"  - evidence_verified_count: {int(metrics.get('evidence_verified_count', 0))}",
        f"  - evidence_failed_count: {int(metrics.get('evidence_failed_count', 0))}",
        f"  - evidence_unresolved_count: {int(metrics.get('evidence_unresolved_count', 0))}",
        f"  - evidence_orphan_count: {int(metrics.get('evidence_orphan_count', 0))}",
        f"  - evidence_unknown_capability_reference_count: {int(metrics.get('evidence_unknown_capability_reference_count', 0))}",
        f"  - evidence_unknown_rule_reference_count: {int(metrics.get('evidence_unknown_rule_reference_count', 0))}",
        f"  - evidence_unknown_pack_reference_count: {int(metrics.get('evidence_unknown_pack_reference_count', 0))}",
        f"  - evidence_deterministic_bundle_mismatch_count: {int(metrics.get('evidence_deterministic_bundle_mismatch_count', 0))}",
        f"  - evidence_deterministic_trust_report_mismatch_count: {int(metrics.get('evidence_deterministic_trust_report_mismatch_count', 0))}",
        f"  - assurance_gate_passed: {int(metrics.get('assurance_gate_passed', 0))}",
        f"  - assurance_fixture_count: {int(metrics.get('assurance_fixture_count', 0))}",
        f"  - assurance_case_count: {int(metrics.get('assurance_case_count', 0))}",
        f"  - assurance_claim_count: {int(metrics.get('assurance_claim_count', 0))}",
        f"  - review_gate_passed: {int(metrics.get('review_gate_passed', 0))}",
        f"  - review_policy_count: {int(metrics.get('review_policy_count', 0))}",
        f"  - review_fixture_count: {int(metrics.get('review_fixture_count', 0))}",
        f"  - review_decision_count: {int(metrics.get('review_decision_count', 0))}",
        f"  - review_expected_decision_mismatch_count: {int(metrics.get('review_expected_decision_mismatch_count', 0))}",
        f"  - review_provenance_replay_mismatch_count: {int(metrics.get('review_provenance_replay_mismatch_count', 0))}",
        f"  - review_provenance_evidence_matrix_mismatch_count: {int(metrics.get('review_provenance_evidence_matrix_mismatch_count', 0))}",
        f"  - review_semantic_diff_deterministic_mismatch_count: {int(metrics.get('review_semantic_diff_deterministic_mismatch_count', 0))}",
        f"  - review_offline_verification_pass_count: {int(metrics.get('review_offline_verification_pass_count', 0))}",
        f"  - review_offline_assurance_claim_count: {int(metrics.get('review_offline_assurance_claim_count', 0))}",
        f"  - review_offline_evidence_matrix_mismatch_count: {int(metrics.get('review_offline_evidence_matrix_mismatch_count', 0))}",
        f"  - review_offline_policy_catalog_mismatch_count: {int(metrics.get('review_offline_policy_catalog_mismatch_count', 0))}",
        f"  - review_portability_violation_count: {int(metrics.get('review_portability_violation_count', 0))}",
        f"  - review_cross_platform_portability_mismatch_count: {int(metrics.get('review_cross_platform_portability_mismatch_count', 0))}",
        f"  - review_cas_object_hash_mismatch_count: {int(metrics.get('review_cas_object_hash_mismatch_count', 0))}",
        f"  - review_cas_deterministic_mismatch_count: {int(metrics.get('review_cas_deterministic_mismatch_count', 0))}",
        f"  - review_predecessor_embedding_mismatch_count: {int(metrics.get('review_predecessor_embedding_mismatch_count', 0))}",
        f"  - review_chain_validation_pass_count: {int(metrics.get('review_chain_validation_pass_count', 0))}",
        f"  - review_chain_length: {int(metrics.get('review_chain_length', 0))}",
        f"  - review_chain_tamper_detection_pass_count: {int(metrics.get('review_chain_tamper_detection_pass_count', 0))}",
        f"  - unexpected_failure_count: {metrics['unexpected_failure_count']}",
        f"  - unsafe_acceptance_count: {metrics['unsafe_acceptance_count']}",
        f"  - unexpected_exception_count: {metrics['unexpected_exception_count']}",
        "Sections:",
    ]
    for name, section in report["sections"].items():
        if section.get("skipped"):
            status = "skipped"
        else:
            status = "passed" if section.get("passed") else "failed"
        lines.append(f"  - {name}: {status}")
    if report["failed_gates"]:
        lines.append("Failed gates:")
        for gate in report["failed_gates"]:
            lines.append(
                f"  - {gate['gate']}: actual {gate['actual']} must be {gate['operator']} {gate['expected']}"
            )
    else:
        lines.append("Failed gates: none")
    lines.append(f"Report path: {report['output_paths']['latest_report']}")
    lines.append(f"Summary path: {report['output_paths']['latest_summary']}")
    lines.append(f"Persistent output dir: {report['persistent_output_dir']}")
    return "\n".join(lines) + "\n"


def write_technical_harness_report(report: dict[str, Any], output_root: str | Path) -> dict[str, Any]:
    """Write latest and persistent technical harness reports."""

    output_path = Path(output_root)
    harness_root = output_path / "harness"
    run_id = report["run_id"]
    run_dir = harness_root / "technical_harness_runs" / run_id
    latest_report_path = harness_root / "technical_harness_report.json"
    latest_summary_path = harness_root / "technical_harness_summary.txt"
    persistent_report_path = run_dir / "technical_harness_report.json"
    persistent_summary_path = run_dir / "technical_harness_summary.txt"
    output_paths = {
        "latest_report": latest_report_path,
        "latest_summary": latest_summary_path,
        "persistent_report": persistent_report_path,
        "persistent_summary": persistent_summary_path,
    }
    report["output_paths"] = json_safe_paths(output_paths)
    report["persistent_output_dir"] = str(run_dir)
    report["summary"] = _build_summary(report)
    _write_json(report, latest_report_path)
    _write_text(report["summary"], latest_summary_path)
    _write_json(report, persistent_report_path)
    _write_text(report["summary"], persistent_summary_path)
    return report


def run_technical_harness(
    output_root: str | Path,
    quick: bool = False,
    include_demo: bool = False,
) -> dict[str, Any]:
    """Run the complete technical harness suite and apply quality gates."""

    _require_cadquery()
    output_path = Path(output_root)
    harness_root = output_path / "harness"
    run_context = create_run_context("technical harness", harness_root, "technical_harness_runs")
    section_output_root = run_context.run_dir / "section_outputs"

    sections = {
        "benchmark": _run_section("benchmark", lambda: _benchmark_section(section_output_root)),
        "sweep": _run_section("sweep", lambda: _sweep_section(section_output_root, quick=quick)),
        "edit_preservation": _run_section(
            "edit_preservation",
            lambda: _edit_preservation_section(section_output_root),
        ),
        "adversarial_rejection": _run_section(
            "adversarial_rejection",
            lambda: _adversarial_section(section_output_root),
        ),
        "volume_delta": _run_section("volume_delta", lambda: _volume_delta_section(run_context.run_dir)),
        "shape_inspection": _run_section(
            "shape_inspection",
            lambda: _shape_inspection_section(run_context.run_dir),
        ),
        "feature_recognition": _run_section(
            "feature_recognition",
            lambda: _feature_recognition_section(run_context.run_dir),
        ),
        "engineering_reasoning": _run_section(
            "engineering_reasoning",
            lambda: _reasoning_section(run_context.run_dir),
        ),
        "rule_packs": _run_section(
            "rule_packs",
            lambda: _rule_pack_section(run_context.run_dir),
        ),
        "capability_coverage": _run_section(
            "capability_coverage",
            lambda: _capability_coverage_section(run_context.run_dir),
        ),
        "evidence_trust": _run_section(
            "evidence_trust",
            lambda: _evidence_trust_section(run_context.run_dir),
        ),
        "assurance": _run_section(
            "assurance",
            lambda: _assurance_section(run_context.run_dir),
        ),
    }
    sections["review_policy"] = _run_section(
        "review_policy",
        lambda: _review_policy_section(run_context.run_dir, sections["assurance"]),
    )
    sections["release_dossier"] = _run_section(
        "release_dossier",
        lambda: _release_dossier_section(run_context.run_dir, sections["review_policy"]),
    )
    if include_demo:
        sections["demo"] = _run_section("demo", lambda: _demo_section(section_output_root))
    else:
        sections["demo"] = {
            "name": "demo",
            "passed": True,
            "skipped": True,
            "reason": "Run with --include-demo to include the demo workflow.",
        }

    report: dict[str, Any] = {
        "run_id": run_context.run_id,
        "created_at": run_context.created_at.isoformat(),
        "quick": quick,
        "include_demo": include_demo,
        "overall_passed": False,
        "quality_gates_passed": False,
        "sections": sections,
        "metrics": _build_metrics(sections),
        "quality_gates": dict(QUALITY_GATES),
        "failed_gates": [],
    }
    gate_result = compute_quality_gates(report)
    report.update(gate_result)
    report["overall_passed"] = report["quality_gates_passed"] and all(
        section.get("passed") or section.get("skipped") for section in sections.values()
    )
    return write_technical_harness_report(report, output_path)
