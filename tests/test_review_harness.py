from pathlib import Path

import pytest

from harness.orchestrator import _assurance_section, _review_policy_section


def test_review_harness_uses_five_assurance_fixtures(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    assurance = _assurance_section(tmp_path)
    review = _review_policy_section(tmp_path, assurance)
    assert review["passed"]
    assert review["review_fixture_count"] == 5
    assert review["accepted_decision_count"] == 4
    assert review["conditional_decision_count"] == 1
    assert review["manual_review_decision_count"] == 0
    assert review["expected_decision_mismatch_count"] == 0
    assert review["review_audit_package_validation_pass_count"] == 5
    assert review["review_provenance_validation_pass_count"] == 5
    assert review["review_provenance_missing_count"] == 0
    assert review["review_provenance_replay_mismatch_count"] == 0
    assert review["review_provenance_evidence_matrix_mismatch_count"] == 0
    assert review["review_semantic_diff_generation_failure_count"] == 0
    assert review["review_semantic_diff_deterministic_mismatch_count"] == 0
    assert review["review_multi_variant_diff_deterministic_mismatch_count"] == 0
    assert review["review_offline_verification_pass_count"] == 5
    assert review["review_offline_assurance_claim_count"] == 49
    assert review["review_offline_evidence_matrix_mismatch_count"] == 0
    assert review["review_offline_policy_catalog_mismatch_count"] == 0
    assert review["review_offline_static_replay_mismatch_count"] == 0
    assert review["review_offline_hash_mismatch_count"] == 0
    assert review["review_portability_violation_count"] == 0
    assert review["review_cross_platform_portability_mismatch_count"] == 0
