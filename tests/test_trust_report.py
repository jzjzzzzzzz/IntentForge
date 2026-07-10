from intentforge.knowledge.trust import generate_trust_report


def test_trust_report_counts_match_phase21_capabilities() -> None:
    report = generate_trust_report()
    assert report.declared_capability_count == 28
    assert report.supported_capability_count == 18
    assert report.partially_supported_capability_count == 5
    assert report.unsupported_boundary_count == 5
    assert report.orphan_evidence_count == 0
    assert report.unknown_capability_reference_count == 0
    assert report.unknown_rule_reference_count == 0
    assert report.unknown_pack_reference_count == 0
    assert report.overall_trust_gate_passed


def test_trust_report_completeness_has_numerators_and_denominators() -> None:
    report = generate_trust_report()
    for metric in (
        report.implementation_evidence_completeness,
        report.verification_evidence_completeness,
        report.boundary_evidence_completeness,
        report.limitation_evidence_completeness,
    ):
        assert {"numerator", "denominator", "value"} <= set(metric)
        assert metric["value"] == 1.0


def test_trust_report_is_deterministic_and_has_no_opaque_score() -> None:
    first = generate_trust_report()
    second = generate_trust_report()
    assert first.report_id == second.report_id
    assert "score" not in first.summary
