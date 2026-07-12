from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from intentforge.assurance.schema import canonical_digest
from intentforge.offline_verify import verify_offline_audit_package
from tests.phase26_test_helpers import build_portable_review_package


@pytest.fixture(scope="module")
def package_template(tmp_path_factory) -> Path:
    return build_portable_review_package(tmp_path_factory.mktemp("offline-package"))


@pytest.fixture
def package(package_template: Path, tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(package_template, target)
    return target


def _canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, separators=(",", ": ")) + "\n").encode()


def _rehash_package(root: Path) -> None:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload_names = sorted(
        item.name for item in root.iterdir()
        if item.is_file() and item.name not in {"manifest.json", "checksums.json"}
    )
    inventory = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in payload_names}
    manifest["file_inventory"] = inventory
    manifest["package_id"] = canonical_digest(
        "audit_package",
        {"assurance_case_id": manifest["assurance_case_id"], "files": inventory},
    )
    manifest_path.write_bytes(_canonical(manifest))
    checksums = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in sorted(root.iterdir())
        if item.is_file() and item.name != "checksums.json"
    }
    (root / "checksums.json").write_bytes(_canonical(checksums))


def test_offline_verifier_validates_complete_frozen_chain(package: Path) -> None:
    result = verify_offline_audit_package(package)
    assert result.passed
    assert result.metrics["rule_snapshot_count"] == 10
    assert result.metrics["capability_snapshot_count"] == 28
    assert result.metrics["evidence_definition_count"] == 65
    assert result.metrics["evidence_observation_count"] == 65
    assert result.metrics["policy_catalog_count"] == 5
    assert result.metrics["policy_catalog_check_count"] == 54
    assert result.metrics["selected_policy_check_count"] == 8
    assert result.metrics["static_check_replay_mismatch_count"] == 0


def test_checksum_tamper_fails_before_static_replay(package: Path) -> None:
    path = package / "assurance_case.json"
    path.write_bytes(path.read_bytes() + b" ")
    result = verify_offline_audit_package(package)
    assert not result.passed
    assert result.failure_stage == "checksum_manifest"
    assert result.metrics["hash_mismatch_count"] >= 1
    assert "static_check_replay_count" not in result.metrics


def test_modified_frozen_snapshot_fails_after_rehashed_inventory(package: Path) -> None:
    provenance_path = package / "review_decision_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["tool_version"] = "tampered"
    provenance_path.write_bytes(_canonical(provenance))
    _rehash_package(package)
    result = verify_offline_audit_package(package)
    assert not result.passed
    assert result.failure_stage == "static_chain"
    assert any("provenance" in error for error in result.errors)


def test_noncanonical_json_is_rejected(package: Path) -> None:
    path = package / "checksums.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(value), encoding="utf-8")
    result = verify_offline_audit_package(package)
    assert not result.passed
    assert result.failure_stage == "canonical_serialization"
    assert result.metrics["canonical_json_mismatch_count"] == 1


def test_duplicate_json_key_is_rejected(package: Path) -> None:
    path = package / "checksums.json"
    path.write_text('{"manifest.json":"x","manifest.json":"y"}\n', encoding="utf-8")
    result = verify_offline_audit_package(package)
    assert not result.passed
    assert result.failure_stage == "checksum_manifest"
    assert any("duplicate JSON key" in error for error in result.errors)


def test_missing_snapshot_file_fails_structure_check(package: Path) -> None:
    (package / "review_policy_catalog_snapshot.json").unlink()
    result = verify_offline_audit_package(package)
    assert not result.passed
    assert result.failure_stage == "package_structure"


def test_symlink_is_rejected(package: Path) -> None:
    try:
        os.symlink(package / "manifest.json", package / "linked.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    result = verify_offline_audit_package(package)
    assert not result.passed
    assert result.failure_stage == "package_structure"
    assert any("symbolic links" in error for error in result.errors)


def test_encoded_traversal_is_rejected_before_identity_checks(package: Path) -> None:
    case_path = package / "assurance_case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["artifact_records"] = [{
        "artifact_id": "artifact_test", "artifact_type": "step", "logical_name": "x.step",
        "path": "%252e%252e/x.step", "content_hash": None, "size": None,
        "producer_operation": "parse_build", "family": "wall_mounted_bracket",
        "request_id": "portable_request", "run_id": "portable_run",
        "validation_status": "not_checked", "metadata_id": "artifact_meta_test",
    }]
    case_path.write_bytes(_canonical(case))
    (package / "artifact_manifest.json").write_bytes(_canonical(case["artifact_records"]))
    provenance_path = package / "review_decision_provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    for snapshot in provenance["snapshots"]:
        if snapshot["snapshot_type"] == "assurance_case":
            snapshot["payload"] = case
    provenance_path.write_bytes(_canonical(provenance))
    decision_path = package / "review_decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["decision_provenance"] = provenance
    decision_path.write_bytes(_canonical(decision))
    _rehash_package(package)
    result = verify_offline_audit_package(package)
    assert not result.passed
    assert result.failure_stage == "portability"
    assert result.metrics["portability_violation_count"] > 0


def test_standalone_verifier_runs_without_site_packages(package: Path) -> None:
    env = {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    completed = subprocess.run(
        [
            sys.executable, "-S", "-c",
            "import sys; from intentforge.offline_verify import verify_offline_audit_package as v; "
            "r=v(sys.argv[1]); print(r.passed, r.metrics['evidence_definition_count'])",
            str(package),
        ],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "True 65"
