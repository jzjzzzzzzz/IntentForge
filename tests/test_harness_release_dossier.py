"""Phase 29: Tests for the harness release-dossier section."""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.orchestrator import _release_dossier_section, _review_policy_section, _assurance_section
from tests.phase27_test_helpers import build_three_package_chain


@pytest.fixture
def populated_run_dir(tmp_path: Path) -> Path:
    chain = build_three_package_chain(tmp_path / "chain")
    review_dir = tmp_path / "review_policy"
    review_dir.mkdir(parents=True, exist_ok=True)
    chain_packages_dir = review_dir / "chain_packages"
    chain_packages_dir.mkdir(parents=True, exist_ok=True)
    for index in range(3):
        target = chain_packages_dir / f"{index}_a"
        target.mkdir(parents=True, exist_ok=True)
        for item in chain["packages"][index].iterdir():
            if item.is_file():
                (target / item.name).write_bytes(item.read_bytes())
    return tmp_path


def test_release_dossier_section_with_synthetic_chain(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "dossier-chain")
    review_dir = tmp_path / "review_policy"
    review_dir.mkdir(parents=True, exist_ok=True)
    chain_packages_dir = review_dir / "chain_packages"
    chain_packages_dir.mkdir(parents=True, exist_ok=True)
    for index in range(3):
        target = chain_packages_dir / f"{index}_a"
        target.mkdir(parents=True, exist_ok=True)
        for item in chain["packages"][index].iterdir():
            if item.is_file():
                (target / item.name).write_bytes(item.read_bytes())
    result = _release_dossier_section(tmp_path, {})
    assert result["passed"] is True
    assert result["release_dossier_validation_pass_count"] == 1
    assert result["release_dossier_merkle_root_count"] == 1
    assert result["release_dossier_tamper_envelope_detection_count"] == 1
    assert result["release_dossier_tamper_leaf_index_detection_count"] == 1
    assert result["release_dossier_tamper_child_detection_count"] == 1


def test_release_dossier_section_insufficient_packages(tmp_path: Path) -> None:
    result = _release_dossier_section(tmp_path, {})
    assert result["passed"] is False
    assert result["chain_package_count"] == 0