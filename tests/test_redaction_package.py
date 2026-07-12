"""Phase 28: Privacy-preserving audit export & verification tests."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from intentforge.cas import store_audit_package
from intentforge.redaction import (
    export_redacted_package,
    verify_redacted_audit_package,
)
from intentforge.redaction.config import (
    RedactionConfig,
    RedactionFieldSelector,
    RedactionRule,
    default_redaction_config,
)
from intentforge.redaction.package import (
    REDACTED_SCHEMA_VERSION,
    REDACTED_ENVELOPE_FILE,
    REDACTION_MANIFEST_FILE,
    RedactedPackageBuilder,
)
from intentforge.redaction.verifier import (
    REDACTED_VERIFIER_VERSION,
    verify_redacted_audit_package as verify_pkg,
)
from tests.phase27_test_helpers import build_three_package_chain


@pytest.fixture(scope="module")
def chain(tmp_path_factory) -> dict:
    return build_three_package_chain(tmp_path_factory.mktemp("redaction-chain"))


def test_redacted_package_uses_content_addressed_envelope(chain: dict) -> None:
    source = chain["packages"][1]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted"
    result = builder.build(source, output_dir)
    assert result["passed"]
    assert result["redacted_package_id"]

    redacted = result["package_path"]
    files = sorted(p.name for p in Path(redacted).iterdir() if p.is_file())
    assert REDACTED_ENVELOPE_FILE in files
    assert REDACTION_MANIFEST_FILE in files


def test_redacted_package_strips_sensitive_data(chain: dict) -> None:
    source = chain["packages"][0]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-strip-test"
    result = builder.build(source, output_dir)
    assert result["passed"]

    redacted = result["package_path"]
    redacted_count = 0
    for json_file in Path(redacted).glob("*.json"):
        if json_file.name in {"manifest.json", "checksums.json", REDACTED_ENVELOPE_FILE, REDACTION_MANIFEST_FILE}:
            continue
        content = json_file.read_text(encoding="utf-8")
        if "[REDACTED" in content:
            redacted_count += 1
    assert redacted_count >= 1


def test_redacted_package_satisfies_offline_verifier(chain: dict) -> None:
    source = chain["packages"][0]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-verified"
    result = builder.build(source, output_dir)
    assert result["passed"]
    verification = verify_redacted_audit_package(result["package_path"])
    assert verification.passed
    assert verification.status == "verified"
    assert verification.original_package_id == result["original_package_id"]
    assert verification.redacted_package_id == result["redacted_package_id"]


def test_redacted_package_preserves_decision_status(chain: dict) -> None:
    source = chain["packages"][1]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-decision"
    result = builder.build(source, output_dir)
    assert result["passed"]

    decision = json.loads((Path(result["package_path"]) / "review_decision.json").read_text(encoding="utf-8"))
    assert decision["decision_status"] in {
        "accepted_within_declared_scope",
        "accepted_with_conditions",
        "rejected_by_policy",
        "manual_review_required",
        "unresolved",
    }


def test_redacted_package_preserves_claim_count(chain: dict) -> None:
    source = chain["packages"][0]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-claims"
    result = builder.build(source, output_dir)
    assert result["passed"]

    case = json.loads((Path(result["package_path"]) / "assurance_case.json").read_text(encoding="utf-8"))
    assert len(case.get("claims", [])) >= 1


def test_redacted_package_preserves_policy_checks(chain: dict) -> None:
    source = chain["packages"][1]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-policy"
    result = builder.build(source, output_dir)
    assert result["passed"]

    policy = json.loads((Path(result["package_path"]) / "review_policy_snapshot.json").read_text(encoding="utf-8"))
    assert len(policy.get("checks", [])) >= 1


def test_redacted_package_does_not_lose_identifier_fields(chain: dict) -> None:
    source = chain["packages"][1]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-ids"
    result = builder.build(source, output_dir)
    assert result["passed"]

    case = json.loads((Path(result["package_path"]) / "assurance_case.json").read_text(encoding="utf-8"))
    for claim in case.get("claims", []):
        assert claim["claim_id"].startswith("claim_")
        assert claim["argument_ids"]
        assert claim.get("content_id")


def test_redacted_package_envelope_is_cryptographically_consistent(chain: dict) -> None:
    source = chain["packages"][1]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-crypt"
    result = builder.build(source, output_dir)
    assert result["passed"]

    envelope = json.loads((Path(result["package_path"]) / REDACTED_ENVELOPE_FILE).read_text(encoding="utf-8"))
    assert envelope["schema_version"] == "1.0"
    assert envelope["hash_algorithm"] == "sha256"
    assert envelope["redacted"] is True
    assert envelope["content_address"].startswith("sha256:")
    assert len(envelope["content_address"]) == 71


def test_redacted_package_preserves_predecessor_pointer(chain: dict) -> None:
    source = chain["packages"][2]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-predecessor"
    result = builder.build(source, output_dir)
    assert result["passed"]

    envelope = json.loads((Path(result["package_path"]) / REDACTED_ENVELOPE_FILE).read_text(encoding="utf-8"))
    assert envelope.get("predecessor_hash_pointer") is not None
    assert envelope["predecessor_hash_pointer"].startswith("sha256:")


def test_redacted_package_tamper_detection(chain: dict) -> None:
    source = chain["packages"][0]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-tamper"
    result = builder.build(source, output_dir)
    assert result["passed"]

    redacted = Path(result["package_path"])
    case_path = redacted / "assurance_case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["overall_assurance_status"] = "tampered_value"
    case_path.write_text(json.dumps(case, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verification = verify_redacted_audit_package(redacted)
    assert not verification.passed


def test_redacted_package_envelope_tamper_detection(chain: dict) -> None:
    source = chain["packages"][0]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-envelope-tamper"
    result = builder.build(source, output_dir)
    assert result["passed"]

    redacted = Path(result["package_path"])
    envelope_path = redacted / REDACTED_ENVELOPE_FILE
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["content_address"] = "sha256:" + "0" * 64
    envelope_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    verification = verify_redacted_audit_package(redacted)
    assert not verification.passed


def test_redacted_package_data_leak_simulation(chain: dict) -> None:
    source = chain["packages"][0]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-leak-simulation"
    result = builder.build(source, output_dir)
    assert result["passed"]

    redacted_dir = Path(result["package_path"])
    sensitive_param_seen = False
    for json_file in redacted_dir.glob("*.json"):
        if json_file.name in {"manifest.json", "checksums.json", REDACTED_ENVELOPE_FILE, REDACTION_MANIFEST_FILE}:
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        as_text = json.dumps(data)
        if "[REDACTED" in as_text:
            sensitive_param_seen = True
            break
    assert sensitive_param_seen, "expected redactions in redacted package"


def test_redacted_package_export_redacted_function(chain: dict) -> None:
    source = chain["packages"][0]
    output_dir = source.parent.parent / "redacted-export-fn"
    result = export_redacted_package(source, output_dir)
    assert result["passed"]
    assert result["redacted_package_id"]


def test_redacted_package_with_predecessor_hash(chain: dict) -> None:
    source = chain["packages"][2]
    predecessor = chain["content_addresses"][1]
    output_dir = source.parent.parent / "redacted-with-predecessor"
    result = export_redacted_package(source, output_dir, predecessor_hash=predecessor)
    assert result["passed"]

    envelope = json.loads((Path(result["package_path"]) / REDACTED_ENVELOPE_FILE).read_text(encoding="utf-8"))
    assert envelope["predecessor_hash_pointer"] == predecessor


def test_redacted_package_custom_config_no_geometry(chain: dict) -> None:
    source = chain["packages"][0]
    config = RedactionConfig(
        description="No redaction",
        rules=[],
    )
    builder = RedactedPackageBuilder(config)
    output_dir = source.parent.parent / "redacted-no-redaction"
    result = builder.build(source, output_dir)
    assert result["passed"]


def test_redacted_package_maximum_preset(chain: dict) -> None:
    source = chain["packages"][1]
    config = RedactionConfig(
        description="Maximum privacy redaction",
        rules=[
            RedactionRule(
                name="all_geometry",
                description="Redact all numeric values",
                severity="high",
                selectors=[{"value_type": "numeric"}],
                token_type="redacted_hash",
                salt="maximum-privacy-salt",
            ),
        ],
    )
    builder = RedactedPackageBuilder(config)
    output_dir = source.parent.parent / "redacted-maximum"
    result = builder.build(source, output_dir)
    assert result["passed"]
    verification = verify_redacted_audit_package(result["package_path"])
    assert verification.passed


def test_redacted_package_id_reference_roundtrip(chain: dict) -> None:
    source = chain["packages"][0]
    builder = RedactedPackageBuilder(default_redaction_config())
    output_dir = source.parent.parent / "redacted-id-roundtrip"
    result = builder.build(source, output_dir)
    assert result["passed"]
    assert result["original_package_id"] == chain["content_addresses"][0]

    verification = verify_redacted_audit_package(result["package_path"])
    assert verification.passed
    assert verification.original_package_id == result["original_package_id"]
    assert verification.redacted_package_id == result["redacted_package_id"]
