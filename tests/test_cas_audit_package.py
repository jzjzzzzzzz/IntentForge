from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from intentforge.cas import cas_storage_path, store_audit_package, verify_audit_chain
from intentforge.offline_verify import verify_offline_audit_package
from tests.phase27_test_helpers import build_three_package_chain


@pytest.fixture(scope="module")
def chain(tmp_path_factory) -> dict:
    return build_three_package_chain(tmp_path_factory.mktemp("cas-chain"))


def test_finalized_package_uses_full_cas_identity(chain: dict) -> None:
    package = chain["packages"][0]
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    envelope = json.loads((package / "cas_envelope.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.2"
    assert manifest["package_id"] == envelope["content_address"]
    assert manifest["package_content_address"] == envelope["content_address"]
    assert envelope["content_address"].startswith("sha256:")
    assert len(envelope["content_address"]) == 71
    assert manifest["cas_object_count"] == len(envelope["objects"]) == 13


def test_every_structural_object_has_exact_sha256_address(chain: dict) -> None:
    package = chain["packages"][1]
    envelope = json.loads((package / "cas_envelope.json").read_text(encoding="utf-8"))
    for item in envelope["objects"]:
        expected = "sha256:" + hashlib.sha256((package / item["logical_path"]).read_bytes()).hexdigest()
        assert item["content_address"] == expected
    verification = verify_offline_audit_package(package)
    assert verification.passed
    assert verification.metrics["cas_object_hash_mismatch_count"] == 0


def test_identical_finalized_packages_have_identical_cas_address(chain: dict, tmp_path: Path) -> None:
    source = chain["packages"][1]
    duplicate = tmp_path / "duplicate"
    shutil.copytree(source, duplicate)
    first = verify_offline_audit_package(source)
    second = verify_offline_audit_package(duplicate)
    assert first.package_id == second.package_id
    assert first.metrics["cas_content_address_verified"] is True


def test_store_reuses_exact_existing_package(chain: dict) -> None:
    package = chain["packages"][0]
    first = store_audit_package(package, chain["store_root"])
    assert first.passed
    assert first.reused_existing is True
    assert Path(first.storage_path) == chain["stored"][0]


def test_store_rejects_different_bytes_at_same_address(chain: dict, tmp_path: Path) -> None:
    store = tmp_path / "store"
    package = chain["packages"][0]
    first = store_audit_package(package, store)
    assert first.passed
    target = Path(first.storage_path)
    (target / "assurance_case.md").write_bytes((target / "assurance_case.md").read_bytes() + b"tamper")
    second = store_audit_package(package, store)
    assert not second.passed
    assert any("different bytes" in error for error in second.errors)


def test_three_package_chain_verifies_deterministically(chain: dict) -> None:
    first = verify_audit_chain(chain["stored"][-1], store_root=chain["store_root"])
    second = verify_audit_chain(chain["stored"][-1], store_root=chain["store_root"])
    assert first.passed
    assert first.chain_length == 3
    assert first.chronological_addresses == tuple(chain["content_addresses"])
    assert first.chain_content_address == second.chain_content_address
    assert first.pointer_mismatch_count == 0


def test_modified_predecessor_breaks_chain(chain: dict, tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(chain["store_root"], store)
    predecessor = cas_storage_path(store, chain["content_addresses"][0])
    target = predecessor / "review_policy_snapshot.json"
    target.write_bytes(target.read_bytes() + b" ")
    result = verify_audit_chain(cas_storage_path(store, chain["content_addresses"][-1]), store_root=store)
    assert not result.passed
    assert result.package_validation_failure_count == 1


def test_deleted_predecessor_breaks_chain(chain: dict, tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(chain["store_root"], store)
    shutil.rmtree(cas_storage_path(store, chain["content_addresses"][0]))
    result = verify_audit_chain(cas_storage_path(store, chain["content_addresses"][-1]), store_root=store)
    assert not result.passed
    assert result.missing_predecessor_count == 1


def test_switched_predecessor_breaks_pointer_chain(chain: dict, tmp_path: Path) -> None:
    store = tmp_path / "store"
    shutil.copytree(chain["store_root"], store)
    expected = cas_storage_path(store, chain["content_addresses"][0])
    replacement = cas_storage_path(store, chain["content_addresses"][1])
    replacement_copy = tmp_path / "replacement"
    shutil.copytree(replacement, replacement_copy)
    shutil.rmtree(expected)
    shutil.copytree(replacement_copy, expected)
    result = verify_audit_chain(cas_storage_path(store, chain["content_addresses"][-1]), store_root=store)
    assert not result.passed
    assert result.pointer_mismatch_count == 1


def test_non_genesis_chain_requires_store_resolution(chain: dict) -> None:
    result = verify_audit_chain(chain["packages"][-1])
    assert not result.passed
    assert result.missing_predecessor_count == 1


def test_cas_envelope_tamper_is_detected_before_chain_use(chain: dict, tmp_path: Path) -> None:
    package = tmp_path / "package"
    shutil.copytree(chain["packages"][0], package)
    envelope_path = package / "cas_envelope.json"
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope["content_address"] = "sha256:" + "0" * 64
    envelope_path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result = verify_offline_audit_package(package)
    assert not result.passed
    assert result.failure_stage == "checksum_manifest"
