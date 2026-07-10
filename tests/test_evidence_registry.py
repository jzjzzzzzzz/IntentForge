import pytest

from intentforge.knowledge.evidence_registry import EvidenceManifestError, EvidenceRegistry, filter_evidence, load_evidence_definitions


def test_evidence_registry_filters() -> None:
    definitions = load_evidence_definitions()
    wall = filter_evidence(definitions, family="wall_mounted_bracket")
    verification = filter_evidence(definitions, role="verification")
    benchmark = filter_evidence(definitions, evidence_type="benchmark_case")
    assert wall
    assert verification
    assert benchmark
    assert all(item.family == "wall_mounted_bracket" for item in wall)
    assert all(item.role == "verification" for item in verification)
    assert all(item.evidence_type == "benchmark_case" for item in benchmark)


def test_evidence_registry_rejects_duplicate_ids() -> None:
    definitions = load_evidence_definitions()
    with pytest.raises(EvidenceManifestError):
        EvidenceRegistry([definitions[0], definitions[0]])


def test_registry_by_capability() -> None:
    registry = EvidenceRegistry(load_evidence_definitions())
    by_capability = registry.by_capability()
    assert "wall_basic_mounting_plate_generation" in by_capability
    assert "l_triangular_gusset" in by_capability
