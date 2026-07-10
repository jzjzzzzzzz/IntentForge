from pathlib import Path

import pytest

from intentforge.knowledge.evidence_registry import (
    EvidenceManifestError,
    load_evidence_manifest,
    validate_evidence_manifest,
)


def test_default_evidence_manifest_loads() -> None:
    manifest = load_evidence_manifest()
    assert manifest.manifest_version == "1.0"
    assert len(manifest.evidence) >= 60


def test_default_evidence_manifest_validates() -> None:
    result = validate_evidence_manifest()
    assert result.passed
    assert result.summary["unknown_capability_reference_count"] == 0
    assert result.summary["unknown_rule_reference_count"] == 0
    assert result.summary["unknown_pack_reference_count"] == 0


def test_malformed_yaml_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(EvidenceManifestError):
        load_evidence_manifest(path)


def test_duplicate_evidence_ids_reported(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        """
manifest_version: "1.0"
evidence:
  - evidence_id: ev_duplicate
    title: One
    description: One.
    evidence_type: documentation
    role: provenance
    reference: docs/validation.md
  - evidence_id: ev_duplicate
    title: Two
    description: Two.
    evidence_type: documentation
    role: provenance
    reference: docs/validation.md
""",
        encoding="utf-8",
    )
    result = validate_evidence_manifest(path=path)
    assert not result.passed
    assert result.summary["duplicate_evidence_id_count"] == 1
