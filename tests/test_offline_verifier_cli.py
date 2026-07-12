from __future__ import annotations

import json
from pathlib import Path

from intentforge.cli import main
from tests.phase26_test_helpers import build_portable_review_package


def test_review_verify_offline_human_output(tmp_path: Path, capsys) -> None:
    package = build_portable_review_package(tmp_path / "package")
    assert main(["review", "verify-offline", str(package)]) == 0
    output = capsys.readouterr().out
    assert "Offline Audit Package Verification" in output
    assert "PASS" in output
    assert "Frozen evidence records: 65" in output
    assert "Policy catalog checks: 54" in output


def test_review_verify_offline_json_output(tmp_path: Path, capsys) -> None:
    package = build_portable_review_package(tmp_path / "package")
    assert main(["review", "verify-offline", str(package), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert payload["status"] == "verified"
    assert payload["metrics"]["offline_registry_access_count"] == 0
    assert payload["metrics"]["network_access_count"] == 0


def test_review_verify_offline_failure_exit_code(tmp_path: Path, capsys) -> None:
    package = build_portable_review_package(tmp_path / "package")
    (package / "review_policy_snapshot.json").write_text("{}\n", encoding="utf-8")
    assert main(["review", "verify-offline", str(package)]) == 1
    assert "FAIL" in capsys.readouterr().out
