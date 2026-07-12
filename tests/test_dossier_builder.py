"""Phase 29: Release dossier builder and rollup tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from intentforge.dossier.builder import (
    DossierLeaf,
    DOSSIER_CHECKSUMS_FILE,
    DOSSIER_ENVELOPE_FILE,
    DOSSIER_LEAF_INDEX_FILE,
    DOSSIER_MANIFEST_FILE,
    DOSSIER_ROLLUP_FILE,
    DOSSIER_SCHEMA_VERSION,
    ROLLOUP_STATUS_APPROVED,
    ROLLOUP_STATUS_APPROVED_WITH_CONDITIONS,
    ROLLOUP_STATUS_BLOCKED,
    ReleaseDossierBuilder,
    compute_dossier_rollup,
    write_dossier,
)
from tests.phase27_test_helpers import build_three_package_chain


@pytest.fixture(scope="module")
def chain(tmp_path_factory) -> dict:
    return build_three_package_chain(tmp_path_factory.mktemp("dossier-chain"))


def _make_leaf(
    address: str,
    *,
    decision_status: str | None = None,
    cad_family: str | None = "wall_mounted_bracket",
) -> DossierLeaf:
    return DossierLeaf(
        leaf_id=f"leaf-{address[:8]}",
        package_path="/tmp/none",
        content_address=address,
        package_kind="standard",
        assurance_case_id=None,
        review_decision_id=None,
        cad_family=cad_family,
        operation="parse_build",
        decision_status=decision_status,
    )


def test_rollup_approved_when_all_children_accepted() -> None:
    leaves = (
        _make_leaf("sha256:" + "a" * 64, decision_status="accepted_within_declared_scope"),
        _make_leaf("sha256:" + "b" * 64, decision_status="accepted_within_declared_scope"),
    )
    rollup = compute_dossier_rollup(leaves)
    assert rollup.rollup_status == ROLLOUP_STATUS_APPROVED
    assert rollup.approved_count == 2
    assert rollup.blocked_count == 0


def test_rollup_blocked_when_any_child_rejected() -> None:
    leaves = (
        _make_leaf("sha256:" + "a" * 64, decision_status="accepted_within_declared_scope"),
        _make_leaf("sha256:" + "b" * 64, decision_status="rejected_by_policy"),
    )
    rollup = compute_dossier_rollup(leaves)
    assert rollup.rollup_status == ROLLOUP_STATUS_BLOCKED
    assert rollup.blocked_count == 1


def test_rollup_blocked_when_any_child_unresolved() -> None:
    leaves = (
        _make_leaf("sha256:" + "a" * 64, decision_status="unresolved"),
    )
    rollup = compute_dossier_rollup(leaves)
    assert rollup.rollup_status == ROLLOUP_STATUS_BLOCKED


def test_rollup_approved_with_conditions_for_conditional_children() -> None:
    leaves = (
        _make_leaf("sha256:" + "a" * 64, decision_status="accepted_within_declared_scope"),
        _make_leaf("sha256:" + "b" * 64, decision_status="accepted_with_conditions"),
    )
    rollup = compute_dossier_rollup(leaves)
    assert rollup.rollup_status == ROLLOUP_STATUS_APPROVED_WITH_CONDITIONS
    assert rollup.conditional_count == 1


def test_rollup_approved_with_conditions_for_manual_review() -> None:
    leaves = (
        _make_leaf("sha256:" + "a" * 64, decision_status="manual_review_required"),
    )
    rollup = compute_dossier_rollup(leaves)
    assert rollup.rollup_status == ROLLOUP_STATUS_APPROVED_WITH_CONDITIONS


def test_rollup_blocked_when_unknown_status_only() -> None:
    leaves = (_make_leaf("sha256:" + "a" * 64, decision_status=None),)
    rollup = compute_dossier_rollup(leaves)
    assert rollup.rollup_status == ROLLOUP_STATUS_BLOCKED


def test_rollup_blocked_when_empty() -> None:
    rollup = compute_dossier_rollup(())
    assert rollup.rollup_status == ROLLOUP_STATUS_BLOCKED
    assert rollup.child_count == 0


def test_rollup_takes_blocking_precedence_over_conditional() -> None:
    leaves = (
        _make_leaf("sha256:" + "a" * 64, decision_status="accepted_with_conditions"),
        _make_leaf("sha256:" + "b" * 64, decision_status="rejected_by_policy"),
    )
    rollup = compute_dossier_rollup(leaves)
    assert rollup.rollup_status == ROLLOUP_STATUS_BLOCKED


def test_dossier_builder_uses_merkle_root(chain: dict) -> None:
    builder = ReleaseDossierBuilder(dossier_id="dossier_test")
    paths = [str(chain["packages"][i]) for i in range(3)]
    dossier = builder.build(paths)
    assert dossier.dossier_id == "dossier_test"
    assert dossier.merkle_tree.root_hash is not None
    assert len(dossier.merkle_tree.leaves) == 3


def test_dossier_builder_rejects_missing_directory(tmp_path: Path) -> None:
    builder = ReleaseDossierBuilder()
    with pytest.raises(ValueError):
        builder.build([tmp_path / "missing"])


def test_dossier_builder_rejects_duplicate_content_address(chain: dict) -> None:
    builder = ReleaseDossierBuilder()
    paths = [str(chain["packages"][0]), str(chain["packages"][0])]
    with pytest.raises(ValueError):
        builder.build(paths)


def test_dossier_leaf_count_matches_packages(chain: dict) -> None:
    builder = ReleaseDossierBuilder()
    paths = [str(chain["packages"][i]) for i in range(2)]
    dossier = builder.build(paths)
    assert len(dossier.leaves) == 2
    assert all(leaf.content_address.startswith("sha256:") for leaf in dossier.leaves)


def test_dossier_deduplicates_concurrent_identical_addresses(chain: dict, tmp_path: Path) -> None:
    shutil_dup = tmp_path / "dup"
    import shutil
    shutil.copytree(chain["packages"][0], shutil_dup)
    builder = ReleaseDossierBuilder()
    with pytest.raises(ValueError):
        builder.build([str(chain["packages"][0]), str(shutil_dup)])


def test_dossier_envelope_has_required_fields(chain: dict) -> None:
    builder = ReleaseDossierBuilder()
    paths = [str(chain["packages"][0])]
    dossier = builder.build(paths)
    envelope = dossier.dossier_envelope
    assert envelope["schema_version"] == DOSSIER_SCHEMA_VERSION
    assert envelope["hash_algorithm"] == "sha256"
    assert envelope["dossier_id"] == dossier.dossier_id
    assert envelope["root_hash"] == dossier.root_hash
    assert envelope["rollup_status"] == dossier.rollup.rollup_status
    assert envelope["content_address"].startswith("sha256:")


def test_dossier_writes_envelope_rollup_and_manifest(chain: dict, tmp_path: Path) -> None:
    builder = ReleaseDossierBuilder()
    paths = [str(chain["packages"][i]) for i in range(3)]
    dossier = builder.build(paths)
    output = tmp_path / "dossier"
    summary = write_dossier(dossier, output)
    assert (output / DOSSIER_ENVELOPE_FILE).is_file()
    assert (output / DOSSIER_ROLLUP_FILE).is_file()
    assert (output / DOSSIER_LEAF_INDEX_FILE).is_file()
    assert (output / DOSSIER_MANIFEST_FILE).is_file()
    assert (output / DOSSIER_CHECKSUMS_FILE).is_file()
    assert summary["leaf_count"] == 3
    assert summary["root_hash"] == dossier.root_hash


def test_dossier_rollup_deterministic_for_same_inputs(chain: dict) -> None:
    paths = [str(chain["packages"][i]) for i in range(3)]
    dossier1 = ReleaseDossierBuilder().build(paths)
    dossier2 = ReleaseDossierBuilder().build(paths)
    assert dossier1.root_hash == dossier2.root_hash
    assert dossier1.rollup.rollup_status == dossier2.rollup.rollup_status