"""Phase 28: CLI commands for privacy-preserving audit export tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from intentforge.redaction.package import (
    REDACTED_ENVELOPE_FILE,
    REDACTION_MANIFEST_FILE,
)
from intentforge.redaction import verify_redacted_audit_package
from tests.phase27_test_helpers import build_three_package_chain


@pytest.fixture(scope="module")
def chain(tmp_path_factory) -> dict:
    return build_three_package_chain(tmp_path_factory.mktemp("cli-redaction-chain"))


def test_cli_export_redacted_creates_package(chain: dict) -> None:
    source = chain["packages"][0]
    output_dir = source.parent.parent / "cli-redacted"

    result = subprocess.run(
        [
            sys.executable, "-m", "intentforge.cli",
            "review", "export-redacted",
            str(source),
            "--output", str(output_dir),
        ],
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output_dir.exists()
    assert (output_dir / REDACTED_ENVELOPE_FILE).exists()


def test_cli_export_redacted_json_format(chain: dict) -> None:
    source = chain["packages"][0]
    output_dir = source.parent.parent / "cli-redacted-json"

    result = subprocess.run(
        [
            sys.executable, "-m", "intentforge.cli",
            "review", "export-redacted",
            str(source),
            "--output", str(output_dir),
            "--json",
        ],
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["passed"] is True
    assert "redacted_package_id" in payload


def test_cli_verify_redacted_passes(chain: dict) -> None:
    source = chain["packages"][0]
    output_dir = source.parent.parent / "cli-verify-redacted"

    export = subprocess.run(
        [
            sys.executable, "-m", "intentforge.cli",
            "review", "export-redacted",
            str(source),
            "--output", str(output_dir),
        ],
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        capture_output=True,
        text=True,
    )
    assert export.returncode == 0, export.stderr

    verify = subprocess.run(
        [
            sys.executable, "-m", "intentforge.cli",
            "review", "verify-redacted",
            str(output_dir),
        ],
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        capture_output=True,
        text=True,
    )
    assert verify.returncode == 0, verify.stderr
    assert "PASS" in verify.stdout


def test_cli_verify_redacted_json(chain: dict) -> None:
    source = chain["packages"][0]
    output_dir = source.parent.parent / "cli-verify-redacted-json"

    export = subprocess.run(
        [
            sys.executable, "-m", "intentforge.cli",
            "review", "export-redacted",
            str(source),
            "--output", str(output_dir),
        ],
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        capture_output=True,
        text=True,
    )
    assert export.returncode == 0, export.stderr

    verify = subprocess.run(
        [
            sys.executable, "-m", "intentforge.cli",
            "review", "verify-redacted",
            str(output_dir),
            "--json",
        ],
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        capture_output=True,
        text=True,
    )
    assert verify.returncode == 0, verify.stderr
    payload = json.loads(verify.stdout)
    assert payload["status"] == "verified"


def test_cli_export_redacted_with_predecessor(chain: dict) -> None:
    source = chain["packages"][2]
    output_dir = source.parent.parent / "cli-redacted-predecessor"

    predecessor = chain["content_addresses"][1]
    result = subprocess.run(
        [
            sys.executable, "-m", "intentforge.cli",
            "review", "export-redacted",
            str(source),
            "--output", str(output_dir),
            "--predecessor", predecessor,
        ],
        cwd=str(Path(__file__).parent.parent),
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert output_dir.exists()
