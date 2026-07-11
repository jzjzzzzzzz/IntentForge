from __future__ import annotations

import json
from pathlib import Path

from intentforge.assurance import build_audit_package
from intentforge.cli import main
from intentforge.review import evaluate_assurance_case, get_review_policy
from tests.review_test_helpers import review_resources, static_case


def _write_decision(tmp_path: Path) -> Path:
    decision = evaluate_assurance_case(
        get_review_policy("intentforge_static_review_v1"),
        static_case(),
        resources=review_resources(),
    )
    path = tmp_path / "decision.json"
    path.write_text(decision.to_json(), encoding="utf-8")
    return path


def test_provenance_cli_reports_static_trace(capsys, tmp_path: Path) -> None:
    path = _write_decision(tmp_path)
    assert main(["review", "provenance", str(path)]) == 0
    output = capsys.readouterr().out
    assert "Review Decision Provenance" in output
    assert "Replay requested: false" in output
    assert "Definitions frozen: 65" in output


def test_provenance_cli_replays_and_returns_json(capsys, tmp_path: Path) -> None:
    path = _write_decision(tmp_path)
    assert main(["review", "provenance", str(path), "--verify", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verification"]["status"] == "verified"
    assert payload["verification"]["replay_performed"] is True
    assert payload["provenance"]["evidence_definition_count"] == 65


def test_provenance_cli_accepts_valid_audit_package(capsys, tmp_path: Path) -> None:
    path = _write_decision(tmp_path)
    decision = json.loads(path.read_text(encoding="utf-8"))
    policy = get_review_policy(decision["policy_id"])
    package = tmp_path / "audit_package"
    build_audit_package(static_case(), package, review_policy=policy, review_decision=decision)
    assert main(["review", "provenance", str(package), "--verify"]) == 0
    assert "Replay performed: true" in capsys.readouterr().out
