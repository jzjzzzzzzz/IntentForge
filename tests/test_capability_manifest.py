import pytest

from intentforge.knowledge.capabilities import CapabilityManifestError, load_capability_manifest
from intentforge.knowledge.coverage import validate_capability_manifest


def test_packaged_capability_manifest_loads() -> None:
    manifest = load_capability_manifest()

    assert manifest.manifest_version == "1.0"
    assert len(manifest.capabilities) >= 20
    assert [capability.capability_id for capability in manifest.capabilities] == [
        capability.capability_id for capability in manifest.capabilities
    ]


def test_packaged_capability_manifest_validates() -> None:
    result = validate_capability_manifest()

    assert result.passed
    assert result.summary["active_rule_count"] == 10
    assert result.summary["mapped_active_rule_count"] == 10
    assert result.summary["orphan_active_rule_count"] == 0
    assert result.summary["unknown_rule_reference_count"] == 0
    assert result.summary["unknown_pack_reference_count"] == 0
    assert result.summary["unknown_evidence_reference_count"] == 0


def test_invalid_yaml_rejected(tmp_path) -> None:
    path = tmp_path / "capabilities.yaml"
    path.write_text("capabilities: [", encoding="utf-8")

    with pytest.raises(Exception):
        load_capability_manifest(path)


def test_duplicate_capability_ids_rejected(tmp_path) -> None:
    path = tmp_path / "capabilities.yaml"
    path.write_text(
        """
manifest_version: "1.0"
capabilities:
  - capability_id: duplicate_capability
    title: One
    description: First.
    family: wall_mounted_bracket
    status: supported
    stages: [parsing]
    implementation_evidence: []
    verification_evidence: []
    version: "1.0"
  - capability_id: duplicate_capability
    title: Two
    description: Second.
    family: wall_mounted_bracket
    status: supported
    stages: [parsing]
    implementation_evidence: []
    verification_evidence: []
    version: "1.0"
""",
        encoding="utf-8",
    )

    with pytest.raises(CapabilityManifestError):
        load_capability_manifest(path)
