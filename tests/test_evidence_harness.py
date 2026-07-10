from harness.orchestrator import _evidence_trust_section, compute_quality_gates


def test_evidence_trust_harness_section(tmp_path) -> None:
    section = _evidence_trust_section(tmp_path)
    assert section["passed"]
    assert section["evidence_manifest_valid"]
    assert section["unknown_capability_reference_count"] == 0
    assert section["deterministic_bundle_mismatch_count"] == 0
    assert section["deterministic_report_mismatch_count"] == 0


def test_evidence_quality_gates() -> None:
    report = {
        "quality_gates": {
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
        },
        "metrics": {
            "evidence_manifest_valid": 1,
            "evidence_duplicate_id_count": 0,
            "evidence_unknown_capability_reference_count": 0,
            "evidence_unknown_rule_reference_count": 0,
            "evidence_unknown_pack_reference_count": 0,
            "evidence_unsafe_file_reference_count": 0,
            "evidence_family_mismatch_count": 0,
            "evidence_stage_mismatch_count": 0,
            "evidence_supported_missing_implementation_count": 0,
            "evidence_supported_missing_verification_count": 0,
            "evidence_partial_missing_limitation_count": 0,
            "evidence_unsupported_missing_boundary_count": 0,
            "evidence_orphan_count": 0,
            "evidence_deterministic_bundle_mismatch_count": 0,
            "evidence_deterministic_trust_report_mismatch_count": 0,
        }
    }
    result = compute_quality_gates(report)
    assert result["quality_gates_passed"]
