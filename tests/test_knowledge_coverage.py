from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.coverage import build_coverage_report, validate_capability_manifest


def test_coverage_report_is_deterministic() -> None:
    first = build_coverage_report()
    second = build_coverage_report()

    assert first.report_id == second.report_id
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_coverage_report_counts() -> None:
    report = build_coverage_report()

    assert report.passed
    assert report.declared_capability_count == 28
    assert report.supported_capability_count == 18
    assert report.partially_supported_capability_count == 5
    assert report.unsupported_capability_count == 5
    assert report.active_rule_count == 10
    assert report.mapped_active_rule_count == 10
    assert report.orphan_active_rule_count == 0
    assert report.implementation_evidence_completeness == 1.0
    assert report.verification_evidence_completeness == 1.0


def test_unknown_rule_reference_fails_validation() -> None:
    manifest = load_capability_manifest().model_copy(deep=True)
    manifest.capabilities[0].rule_ids.append("missing_rule_999")

    result = validate_capability_manifest(manifest)

    assert not result.passed
    assert "missing_rule_999" in result.summary["unknown_rule_references"]


def test_unknown_pack_reference_fails_validation() -> None:
    manifest = load_capability_manifest().model_copy(deep=True)
    manifest.capabilities[0].knowledge_packs.append("missing_pack")

    result = validate_capability_manifest(manifest)

    assert not result.passed
    assert "missing_pack" in result.summary["unknown_pack_references"]


def test_supported_capability_without_implementation_evidence_fails() -> None:
    manifest = load_capability_manifest().model_copy(deep=True)
    supported = next(capability for capability in manifest.capabilities if capability.status == "supported")
    supported.implementation_evidence.clear()

    result = validate_capability_manifest(manifest)

    assert not result.passed
    assert supported.capability_id in result.summary["supported_capabilities_missing_implementation_evidence"]


def test_supported_capability_without_verification_evidence_fails() -> None:
    manifest = load_capability_manifest().model_copy(deep=True)
    supported = next(capability for capability in manifest.capabilities if capability.status == "supported")
    supported.verification_evidence.clear()

    result = validate_capability_manifest(manifest)

    assert not result.passed
    assert supported.capability_id in result.summary["supported_capabilities_missing_verification_evidence"]


def test_unsupported_capability_without_rejection_evidence_fails() -> None:
    manifest = load_capability_manifest().model_copy(deep=True)
    unsupported = next(capability for capability in manifest.capabilities if capability.status == "unsupported")
    unsupported.verification_evidence.clear()

    result = validate_capability_manifest(manifest)

    assert not result.passed
    assert unsupported.capability_id in result.summary["unsupported_capabilities_missing_rejection_or_boundary_evidence"]


def test_duplicate_evidence_reference_fails() -> None:
    manifest = load_capability_manifest().model_copy(deep=True)
    capability = manifest.capabilities[0]
    capability.implementation_evidence.append(capability.implementation_evidence[0].model_copy(deep=True))

    result = validate_capability_manifest(manifest)

    assert not result.passed
    assert result.summary["duplicate_evidence_reference_count"] == 1
