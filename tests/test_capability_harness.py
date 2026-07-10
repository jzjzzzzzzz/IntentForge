from harness.orchestrator import _capability_coverage_section, compute_quality_gates


def test_capability_coverage_harness_section(tmp_path) -> None:
    section = _capability_coverage_section(tmp_path)

    assert section["passed"]
    assert section["capability_manifest_valid"]
    assert section["capability_count"] == 28
    assert section["active_rule_count"] == 10
    assert section["orphan_rule_count"] == 0
    assert section["unknown_reference_count"] == 0


def test_capability_quality_gates_pass_for_good_metrics() -> None:
    report = {
        "metrics": {
            "benchmark_pass_rate": 1.0,
            "sweep_pass_rate": 1.0,
            "edit_preservation_rate": 1.0,
            "adversarial_rejection_success_rate": 1.0,
            "reasoning_generation_pass_rate": 1.0,
            "unexpected_failure_count": 0,
            "unsafe_acceptance_count": 0,
            "unexpected_exception_count": 0,
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
            "capability_duplicate_id_count": 0,
            "capability_unknown_reference_count": 0,
            "capability_supported_missing_implementation_count": 0,
            "capability_supported_missing_verification_count": 0,
            "capability_partial_missing_limitation_count": 0,
            "capability_unsupported_missing_boundary_count": 0,
            "capability_orphan_rule_count": 0,
            "capability_nondeterministic_report_count": 0,
        }
    }

    result = compute_quality_gates(report)

    assert result["quality_gates_passed"]


def test_capability_quality_gate_fails_unknown_references() -> None:
    report = {
        "metrics": {
            "benchmark_pass_rate": 1.0,
            "sweep_pass_rate": 1.0,
            "edit_preservation_rate": 1.0,
            "adversarial_rejection_success_rate": 1.0,
            "reasoning_generation_pass_rate": 1.0,
            "unexpected_failure_count": 0,
            "unsafe_acceptance_count": 0,
            "unexpected_exception_count": 0,
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
            "capability_duplicate_id_count": 0,
            "capability_unknown_reference_count": 1,
            "capability_supported_missing_implementation_count": 0,
            "capability_supported_missing_verification_count": 0,
            "capability_partial_missing_limitation_count": 0,
            "capability_unsupported_missing_boundary_count": 0,
            "capability_orphan_rule_count": 0,
            "capability_nondeterministic_report_count": 0,
        }
    }

    result = compute_quality_gates(report)

    assert not result["quality_gates_passed"]
    assert any(gate["gate"] == "capability_unknown_reference_count_max" for gate in result["failed_gates"])
