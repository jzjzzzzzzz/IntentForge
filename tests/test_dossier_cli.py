"""Phase 29: CLI tests for dossier build and verify commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from intentforge.dossier import (
    DOSSIER_ENVELOPE_FILE,
    DOSSIER_ROLLUP_FILE,
    ReleaseDossierBuilder,
    write_dossier,
)
from tests.phase27_test_helpers import build_three_package_chain


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "intentforge.cli", "review", *args],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "./src", "PATH": "/usr/bin:/bin"},
    )


def test_build_dossier_cli_writes_files(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "cli-chain")
    output = tmp_path / "dossier"
    paths = [str(chain["packages"][i]) for i in range(3)]
    proc = _run_cli("build-dossier", *paths, "--output", str(output))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (output / DOSSIER_ENVELOPE_FILE).is_file()
    assert (output / DOSSIER_ROLLUP_FILE).is_file()
    assert "PASS" in proc.stdout
    assert "release_" in proc.stdout


def test_build_dossier_cli_json_output(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "json-chain")
    output = tmp_path / "dossier"
    paths = [str(chain["packages"][0])]
    proc = _run_cli("build-dossier", *paths, "--output", str(output), "--json")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["passed"] is True
    assert payload["leaf_count"] == 1
    assert payload["root_hash"].startswith("sha256:")


def test_verify_dossier_cli_accepts_clean_dossier(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "verify-chain")
    paths = [str(chain["packages"][i]) for i in range(3)]
    dossier = ReleaseDossierBuilder().build(paths)
    output = tmp_path / "dossier"
    write_dossier(dossier, output)
    proc = _run_cli("verify-dossier", str(output))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout
    assert "verified" in proc.stdout.lower() or "release_" in proc.stdout


def test_verify_dossier_cli_detects_tampered_envelope(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "tamper-chain")
    paths = [str(chain["packages"][i]) for i in range(3)]
    dossier = ReleaseDossierBuilder().build(paths)
    output = tmp_path / "dossier"
    write_dossier(dossier, output)
    envelope = output / DOSSIER_ENVELOPE_FILE
    data = json.loads(envelope.read_text(encoding="utf-8"))
    data["root_hash"] = "sha256:" + "0" * 64
    envelope.write_text(json.dumps(data), encoding="utf-8")
    proc = _run_cli("verify-dossier", str(output))
    assert proc.returncode == 1
    assert "FAIL" in proc.stdout


def test_verify_dossier_cli_json_output(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "json-verify-chain")
    paths = [str(chain["packages"][i]) for i in range(3)]
    dossier = ReleaseDossierBuilder().build(paths)
    output = tmp_path / "dossier"
    write_dossier(dossier, output)
    proc = _run_cli("verify-dossier", str(output), "--json")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["passed"] is True
    assert payload["child_count"] == 3


def test_build_dossier_cli_rejects_duplicate_addresses(tmp_path: Path) -> None:
    chain = build_three_package_chain(tmp_path / "dup-chain")
    output = tmp_path / "dossier"
    proc = _run_cli(
        "build-dossier",
        str(chain["packages"][0]),
        str(chain["packages"][0]),
        "--output", str(output),
    )
    assert proc.returncode == 1
    assert "FAIL" in proc.stdout


def test_verify_dossier_cli_handles_missing_directory(tmp_path: Path) -> None:
    proc = _run_cli("verify-dossier", str(tmp_path / "missing"))
    assert proc.returncode == 1