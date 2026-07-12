"""Phase 29: Release dossier recursive verifier tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from intentforge.dossier import (
    DOSSIER_CHECKSUMS_FILE,
    DOSSIER_ENVELOPE_FILE,
    DOSSIER_LEAF_INDEX_FILE,
    DOSSIER_MANIFEST_FILE,
    ReleaseDossierBuilder,
    compute_dossier_rollup,
    verify_release_dossier,
    write_dossier,
)
from tests.phase27_test_helpers import build_three_package_chain


@pytest.fixture(scope="module")
def chain(tmp_path_factory) -> dict:
    return build_three_package_chain(tmp_path_factory.mktemp("dossier-verify-chain"))


def _build_and_write(chain: dict, tmp_path: Path) -> tuple[Path, Path]:
    paths = [str(chain["packages"][i]) for i in range(3)]
    dossier = ReleaseDossierBuilder().build(paths)
    output = tmp_path / "dossier"
    write_dossier(dossier, output)
    return output, Path(chain["packages"][0])


def test_verify_dossier_accepts_clean_dossier(chain: dict, tmp_path: Path) -> None:
    output, _ = _build_and_write(chain, tmp_path)
    result = verify_release_dossier(output)
    assert result.passed
    assert result.status == "verified"
    assert result.child_count == 3
    assert result.passed_child_count == 3
    assert result.failed_child_count == 0
    assert result.dossier_id is not None
    assert result.root_hash is not None


def test_verify_dossier_detects_tampered_envelope(chain: dict, tmp_path: Path) -> None:
    output, _ = _build_and_write(chain, tmp_path)
    envelope_path = output / DOSSIER_ENVELOPE_FILE
    payload = json.loads(envelope_path.read_text(encoding="utf-8"))
    payload["root_hash"] = "sha256:" + "f" * 64
    envelope_path.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_release_dossier(output)
    assert not result.passed
    assert result.failure_stage in {"dossier_envelope", "static_dossier_validation"}
    assert any("root" in error for error in result.errors)


def test_verify_dossier_detects_checksum_mismatch(chain: dict, tmp_path: Path) -> None:
    output, _ = _build_and_write(chain, tmp_path)
    manifest_path = output / DOSSIER_MANIFEST_FILE
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "rollup_status" in payload:
        payload["rollup_status"] = "tampered"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_release_dossier(output)
    assert not result.passed
    assert any("checksum" in error for error in result.errors)


def test_verify_dossier_detects_tampered_leaf_index(chain: dict, tmp_path: Path) -> None:
    output, _ = _build_and_write(chain, tmp_path)
    index_path = output / DOSSIER_LEAF_INDEX_FILE
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload[0]["content_address"] = "sha256:" + "0" * 64
    index_path.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_release_dossier(output)
    assert not result.passed
    assert any("leaf index" in error for error in result.errors)


def test_verify_dossier_detects_merkle_root_mismatch(chain: dict, tmp_path: Path) -> None:
    output, _ = _build_and_write(chain, tmp_path)
    envelope_path = output / DOSSIER_ENVELOPE_FILE
    payload = json.loads(envelope_path.read_text(encoding="utf-8"))
    payload["leaf_addresses"] = ["sha256:" + "0" * 64]
    envelope_path.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_release_dossier(output)
    assert not result.passed
    assert any("leaf_addresses" in error or "root" in error for error in result.errors)


def test_verify_dossier_detects_tampered_child_package(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "tamper-chain")
    output, child_pkg = _build_and_write(chain, tmp_path)
    target = chain["packages"][0] / "review_decision.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    payload["decision_status"] = "rejected_by_policy"
    target.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_release_dossier(output)
    assert not result.passed
    assert result.failed_child_count >= 1


def test_verify_dossier_detects_missing_child_directory(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "missing-chain")
    output, child_pkg = _build_and_write(chain, tmp_path)
    shutil.rmtree(child_pkg)
    result = verify_release_dossier(output)
    assert not result.passed


def test_verify_dossier_rollup_matches_when_children_approved(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "rollup-chain")
    paths = [str(chain["packages"][i]) for i in range(2)]
    dossier = ReleaseDossierBuilder().build(paths)
    output = tmp_path / "dossier"
    write_dossier(dossier, output)
    result = verify_release_dossier(output)
    assert result.passed
    assert result.rollup_status == dossier.rollup.rollup_status


def test_verify_dossier_handles_missing_directory(tmp_path: Path) -> None:
    result = verify_release_dossier(tmp_path / "missing")
    assert not result.passed
    assert result.failure_stage == "package_structure"


def test_verify_dossier_serializes_to_json(chain: dict, tmp_path: Path) -> None:
    output, _ = _build_and_write(chain, tmp_path)
    result = verify_release_dossier(output)
    payload = result.to_dict()
    json.dumps(payload, sort_keys=True)
    assert "dossier_verifier_version" in payload
    assert payload["child_count"] == 3


def test_verify_dossier_envelope_address_verification(chain: dict, tmp_path: Path) -> None:
    output, _ = _build_and_write(chain, tmp_path)
    envelope_path = output / DOSSIER_ENVELOPE_FILE
    payload = json.loads(envelope_path.read_text(encoding="utf-8"))
    payload.pop("content_address", None)
    envelope_path.write_text(json.dumps(payload), encoding="utf-8")
    result = verify_release_dossier(output)
    assert not result.passed
    assert any("content address" in error for error in result.errors)


def test_verify_dossier_rollup_blocked_when_any_rejected(
    tmp_path: Path,
) -> None:
    chain = build_three_package_chain(tmp_path / "blocked-chain")
    paths = [str(chain["packages"][i]) for i in range(3)]
    for idx, status in enumerate(["rejected_by_policy", "accepted_within_declared_scope", "accepted_within_declared_scope"]):
        target = chain["packages"][idx] / "review_decision.json"
        payload = json.loads(target.read_text(encoding="utf-8"))
        payload["decision_status"] = status
        target.write_text(json.dumps(payload), encoding="utf-8")
    dossier = ReleaseDossierBuilder().build(paths)
    assert dossier.rollup.rollup_status == "release_blocked"
    output = tmp_path / "dossier"
    write_dossier(dossier, output)
    result = verify_release_dossier(output)
    assert result.rollup_status == "release_blocked"