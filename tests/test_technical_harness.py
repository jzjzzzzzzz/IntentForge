import json
from pathlib import Path

import pytest

from harness.orchestrator import (
    QUALITY_GATES,
    compute_quality_gates,
    run_technical_harness,
    write_technical_harness_report,
)
from intentforge.cli import main
from intentforge.generator.cadquery_generator import CadQueryUnavailableError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _metrics(**overrides):
    metrics = {
        "benchmark_pass_rate": 1.0,
        "sweep_pass_rate": 1.0,
        "edit_preservation_rate": 1.0,
        "adversarial_rejection_success_rate": 1.0,
        "reasoning_generation_pass_rate": 1.0,
        "unknown_rule_reference_count": 0,
        "duplicate_recommendation_count": 0,
        "missing_limitation_count": 0,
        "recommendation_contradiction_count": 0,
        "recommendation_applicability_error_count": 0,
        "nondeterministic_reasoning_report_count": 0,
        "reasoning_report_id_mismatch_count": 0,
        "rule_pack_load_pass_rate": 1.0,
        "active_pack_count": 4,
        "active_rule_count": 10,
        "duplicate_pack_id_count": 0,
        "duplicate_rule_id_count": 0,
        "invalid_pack_count": 0,
        "rule_pack_unknown_rule_reference_count": 0,
        "legacy_compatibility_passed": 1,
        "rule_pack_reasoning_regression_pass_rate": 1.0,
        "capability_manifest_valid": 1,
        "capability_count": 28,
        "supported_capability_count": 18,
        "partial_capability_count": 5,
        "unsupported_capability_count": 5,
        "capability_active_rule_count": 10,
        "capability_mapped_rule_count": 10,
        "capability_orphan_rule_count": 0,
        "capability_unknown_reference_count": 0,
        "capability_duplicate_id_count": 0,
        "capability_supported_missing_implementation_count": 0,
        "capability_supported_missing_verification_count": 0,
        "capability_partial_missing_limitation_count": 0,
        "capability_unsupported_missing_boundary_count": 0,
        "capability_implementation_evidence_completeness": 1.0,
        "capability_verification_evidence_completeness": 1.0,
        "capability_nondeterministic_report_count": 0,
        "evidence_manifest_valid": 1,
        "evidence_definition_count": 65,
        "evidence_required_count": 65,
        "evidence_verified_count": 65,
        "evidence_failed_count": 0,
        "evidence_unresolved_count": 0,
        "evidence_unavailable_count": 0,
        "evidence_stale_count": 0,
        "evidence_orphan_count": 0,
        "evidence_duplicate_id_count": 0,
        "evidence_duplicate_reference_count": 0,
        "evidence_family_mismatch_count": 0,
        "evidence_stage_mismatch_count": 0,
        "evidence_unknown_capability_reference_count": 0,
        "evidence_unknown_rule_reference_count": 0,
        "evidence_unknown_pack_reference_count": 0,
        "evidence_unsafe_file_reference_count": 0,
        "evidence_supported_missing_implementation_count": 0,
        "evidence_supported_missing_verification_count": 0,
        "evidence_partial_missing_limitation_count": 0,
        "evidence_unsupported_missing_boundary_count": 0,
        "evidence_deterministic_bundle_mismatch_count": 0,
        "evidence_deterministic_trust_report_mismatch_count": 0,
        "assurance_gate_passed": 1,
        "assurance_fixture_count": 5,
        "assurance_case_count": 5,
        "assurance_claim_count": 1,
        "assurance_invalid_capability_reference_count": 0,
        "assurance_invalid_evidence_reference_count": 0,
        "assurance_invalid_rule_reference_count": 0,
        "assurance_unsafe_artifact_path_count": 0,
        "assurance_missing_required_validation_count": 0,
        "assurance_deterministic_case_mismatch_count": 0,
        "assurance_deterministic_package_mismatch_count": 0,
        "assurance_package_hash_mismatch_count": 0,
        "review_gate_passed": 1,
        "review_policy_manifest_valid": 1,
        "review_policy_count": 5,
        "review_invalid_policy_count": 0,
        "review_fixture_count": 5,
        "review_decision_count": 5,
        "review_accepted_decision_count": 4,
        "review_conditional_decision_count": 1,
        "review_manual_review_decision_count": 0,
        "review_rejected_decision_count": 0,
        "review_unresolved_decision_count": 0,
        "review_unknown_claim_reference_count": 0,
        "review_unknown_validation_reference_count": 0,
        "review_unknown_capability_reference_count": 0,
        "review_unknown_evidence_reference_count": 0,
        "review_unknown_rule_reference_count": 0,
        "review_policy_scope_mismatch_count": 0,
        "review_unsafe_path_count": 0,
        "review_deterministic_finding_mismatch_count": 0,
        "review_deterministic_condition_mismatch_count": 0,
        "review_deterministic_decision_mismatch_count": 0,
        "review_audit_package_hash_mismatch_count": 0,
        "review_expected_decision_mismatch_count": 0,
        "review_full_policy_incompatible_acceptance_count": 0,
        "review_provenance_validation_pass_count": 5,
        "review_provenance_missing_count": 0,
        "review_provenance_snapshot_mismatch_count": 0,
        "review_provenance_execution_node_mismatch_count": 0,
        "review_provenance_replay_mismatch_count": 0,
        "review_provenance_evidence_matrix_mismatch_count": 0,
        "review_deterministic_provenance_mismatch_count": 0,
        "review_semantic_diff_count": 1,
        "review_semantic_diff_generation_failure_count": 0,
        "review_semantic_diff_deterministic_mismatch_count": 0,
        "review_multi_variant_diff_deterministic_mismatch_count": 0,
        "unexpected_failure_count": 0,
        "unsafe_acceptance_count": 0,
        "unexpected_exception_count": 0,
    }
    metrics.update(overrides)
    return metrics


def _minimal_report(run_id: str = "technical_harness_unit") -> dict:
    return {
        "run_id": run_id,
        "created_at": "2026-07-09T00:00:00+00:00",
        "quick": True,
        "include_demo": False,
        "overall_passed": True,
        "quality_gates_passed": True,
        "sections": {
            "benchmark": {"passed": True},
            "sweep": {"passed": True},
            "edit_preservation": {"passed": True},
            "adversarial_rejection": {"passed": True},
            "volume_delta": {"passed": True},
            "shape_inspection": {"passed": True},
            "engineering_reasoning": {"passed": True},
            "rule_packs": {"passed": True},
            "capability_coverage": {"passed": True},
            "evidence_trust": {"passed": True},
            "assurance": {"passed": True},
            "review_policy": {"passed": True},
            "demo": {"passed": True, "skipped": True},
        },
        "metrics": _metrics(),
        "quality_gates": dict(QUALITY_GATES),
        "failed_gates": [],
    }


def test_orchestrator_imports() -> None:
    assert callable(run_technical_harness)
    assert callable(write_technical_harness_report)


def test_quality_gate_computation_passes_for_good_report() -> None:
    result = compute_quality_gates(
        {
            "metrics": _metrics(),
            "quality_gates": dict(QUALITY_GATES),
        }
    )

    assert result["quality_gates_passed"] is True
    assert result["failed_gates"] == []


def test_quality_gate_computation_fails_for_bad_report() -> None:
    result = compute_quality_gates(
        {
            "metrics": _metrics(
                benchmark_pass_rate=0.5,
                unsafe_acceptance_count=1,
                unexpected_exception_count=1,
            ),
            "quality_gates": dict(QUALITY_GATES),
        }
    )

    failed_gate_names = {gate["gate"] for gate in result["failed_gates"]}
    assert result["quality_gates_passed"] is False
    assert "benchmark_pass_rate_min" in failed_gate_names
    assert "unsafe_acceptance_count_max" in failed_gate_names
    assert "unexpected_exception_count_max" in failed_gate_names


def test_report_writing_creates_latest_and_persistent_files(tmp_path: Path) -> None:
    report = write_technical_harness_report(_minimal_report(), tmp_path / "output")

    latest_report = Path(report["output_paths"]["latest_report"])
    latest_summary = Path(report["output_paths"]["latest_summary"])
    persistent_report = Path(report["output_paths"]["persistent_report"])
    persistent_summary = Path(report["output_paths"]["persistent_summary"])

    assert latest_report.exists()
    assert latest_summary.exists()
    assert persistent_report.exists()
    assert persistent_summary.exists()
    written = json.loads(latest_report.read_text(encoding="utf-8"))
    assert written["run_id"] == "technical_harness_unit"
    assert "Quality gates passed: true" in latest_summary.read_text(encoding="utf-8")


def test_run_technical_harness_requires_cadquery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import harness.orchestrator as orchestrator

    monkeypatch.setattr(orchestrator, "_cadquery_available", lambda: False)

    with pytest.raises(CadQueryUnavailableError, match="CadQuery is required"):
        run_technical_harness(tmp_path / "output", quick=True)


def test_cli_technical_harness_quick_runs_when_cadquery_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("cadquery")
    monkeypatch.chdir(PROJECT_ROOT)

    result = main(["technical-harness", "--quick"])

    assert result == 0
    report_path = PROJECT_ROOT / "output" / "harness" / "technical_harness_report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["quick"] is True
    assert report["overall_passed"] is True
    assert report["quality_gates_passed"] is True
