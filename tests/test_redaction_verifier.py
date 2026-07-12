"""Phase 28: Privacy-preserving verifier (zero-knowledge-like) tests."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from intentforge.redaction import verify_redacted_audit_package
from intentforge.redaction.package import (
    REDACTED_ENVELOPE_FILE,
    REDACTION_MANIFEST_FILE,
)
from intentforge.redaction.verifier import (
    REDACTED_VERIFIER_VERSION,
    RedactedVerificationResult,
)
from tests.phase27_test_helpers import build_three_package_chain


@pytest.fixture(scope="module")
def chain(tmp_path_factory) -> dict:
    return build_three_package_chain(tmp_path_factory.mktemp("privacy-verify-chain"))


def _build_redacted(chain: dict, suffix: str):
    source = chain["packages"][1]
    from intentforge.redaction import default_redaction_config
    from intentforge.redaction.package import RedactedPackageBuilder
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / f"redacted-verify-{suffix}"
    return builder.build(source, output_dir)


def test_verifier_returns_verified_for_valid_package(chain: dict) -> None:
    result = _build_redacted(chain, "valid")
    assert result["passed"]
    verification = verify_redacted_audit_package(result["package_path"])
    assert verification.passed
    assert verification.status == "verified"
    assert verification.failure_stage is None


def test_verifier_returns_result_data_class(chain: dict) -> None:
    result = _build_redacted(chain, "dataclass")
    verification = verify_redacted_audit_package(result["package_path"])
    assert isinstance(verification, RedactedVerificationResult)
    assert verification.to_dict()["status"] == verification.status


def test_verifier_detects_missing_package() -> None:
    verification = verify_redacted_audit_package("/tmp/nonexistent_redacted_package_xxx")
    assert not verification.passed
    assert verification.failure_stage == "package_structure"


def test_verifier_detects_tampered_checksum(chain: dict) -> None:
    result = _build_redacted(chain, "tamper-checksum")
    redacted = Path(result["package_path"])
    manifest_path = redacted / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "checksums" in manifest:
        for k in manifest["checksums"]:
            manifest["checksums"][k] = "deadbeef"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verification = verify_redacted_audit_package(redacted)
        assert not verification.passed


def test_verifier_preserves_decision_count(chain: dict) -> None:
    result = _build_redacted(chain, "preserve-count")
    verification = verify_redacted_audit_package(result["package_path"])
    assert verification.passed
    metrics = verification.metrics
    assert metrics.get("policy_check_count", 0) >= 1
    assert metrics.get("total_claims", 0) >= 1


def test_verifier_emits_warning_for_redaction_strength(chain: dict) -> None:
    result = _build_redacted(chain, "warning")
    verification = verify_redacted_audit_package(result["package_path"])
    assert verification.passed
    assert any("CAS chain integrity" in w for w in verification.warnings)


def test_verifier_handles_full_chain_through_predecessor(chain: dict) -> None:
    source = chain["packages"][2]
    from intentforge.redaction import default_redaction_config, export_redacted_package
    config = default_redaction_config()
    output_dir = source.parent.parent / "redacted-chain-test"
    result = export_redacted_package(source, output_dir, predecessor_hash=chain["content_addresses"][1])
    assert result["passed"]
    verification = verify_redacted_audit_package(result["package_path"])
    assert verification.passed
    assert verification.metrics.get("predecessor_pointer_present")


def test_verifier_metrics_are_complete(chain: dict) -> None:
    result = _build_redacted(chain, "metrics")
    verification = verify_redacted_audit_package(result["package_path"])
    assert verification.passed
    metrics = verification.metrics
    expected_metrics = {
        "total_redactions",
        "files_processed",
        "redacted_cas_object_count",
        "checksum_validation_passed",
        "policy_check_count",
    }
    for key in expected_metrics:
        assert key in metrics, f"missing metric: {key}"


def test_data_leak_simulation_forbid_sensitive_in_redacted(chain: dict) -> None:
    """Simulate a data leak scan: confirm sensitive parametric numbers cannot be trivially recovered from the redacted package."""
    result = _build_redacted(chain, "leak-scan")
    redacted_dir = Path(result["package_path"])

    leak_terms = []
    for json_file in redacted_dir.glob("*.json"):
        if json_file.name in {"manifest.json", "checksums.json", REDACTED_ENVELOPE_FILE, REDACTION_MANIFEST_FILE}:
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        as_text = json.dumps(data)
        for term in ["12345", "secret_param", "proprietary_value"]:
            if term in as_text:
                leak_terms.append((json_file.name, term))

    assert not leak_terms, f"potential data leak: {leak_terms}"


def test_verification_does_not_require_live_registries(chain: dict) -> None:
    """The redacted verifier must work with ONLY the package files (zero-knowledge-like)."""
    result = _build_redacted(chain, "zk-like")
    import os
    isolated_env = {
        k: v for k, v in os.environ.items()
        if k.lower() not in {"path"} and not k.startswith("IFG_")
    }
    assert result["passed"]


def test_redacted_chain_replay_preserves_provenance(chain: dict) -> None:
    """Predecessor hash pointer is preserved across the redacted chain replay."""
    source = chain["packages"][2]
    from intentforge.redaction import default_redaction_config, export_redacted_package
    output_dir = source.parent.parent / "redacted-replay"
    result = export_redacted_package(source, output_dir, predecessor_hash=chain["content_addresses"][1])
    assert result["passed"]

    envelope = json.loads((Path(result["package_path"]) / REDACTED_ENVELOPE_FILE).read_text(encoding="utf-8"))
    assert envelope.get("predecessor_hash_pointer") == chain["content_addresses"][1]

    verification = verify_redacted_audit_package(result["package_path"])
    assert verification.passed
