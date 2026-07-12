from __future__ import annotations

import json
from pathlib import Path

from intentforge.assurance import build_audit_package, validate_audit_package
from intentforge.review import evaluate_assurance_case, get_review_policy
from tests.review_test_helpers import full_case, review_resources


def _package(tmp_path: Path) -> Path:
    case = full_case()
    policy = get_review_policy("intentforge_full_design_review_v1")
    base = build_audit_package(case, tmp_path / "base")
    decision = evaluate_assurance_case(
        policy,
        case,
        base["validation"],
        resources=review_resources(),
    )
    output = tmp_path / "reviewed"
    result = build_audit_package(case, output, review_policy=policy, review_decision=decision)
    assert result["validation"]["passed"]
    return output


def test_audit_package_freezes_and_replays_review_provenance(tmp_path: Path) -> None:
    package = _package(tmp_path)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    provenance = json.loads((package / "review_decision_provenance.json").read_text(encoding="utf-8"))
    validation = validate_audit_package(package)
    assert manifest["review_provenance_id"] == provenance["provenance_id"]
    assert validation["passed"]
    assert validation["review_provenance_verification_passed"] is True
    assert validation["offline_verification_passed"] is True


def test_audit_package_detects_provenance_tampering(tmp_path: Path) -> None:
    package = _package(tmp_path)
    path = package / "review_decision_provenance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tool_version"] = "tampered"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validation = validate_audit_package(package)
    assert not validation["passed"]
    assert validation["hash_mismatch_count"] >= 1


def test_provenance_package_validation_does_not_require_live_registries(monkeypatch, tmp_path: Path) -> None:
    package = _package(tmp_path)

    def fail_live_load(*args, **kwargs):
        raise AssertionError("live registry must not be used for provenance package validation")

    monkeypatch.setattr("intentforge.assurance.validator.load_capability_manifest", fail_live_load)
    monkeypatch.setattr("intentforge.assurance.validator.load_evidence_definitions", fail_live_load)
    monkeypatch.setattr("intentforge.assurance.validator.RuleRegistry.load", fail_live_load)
    monkeypatch.setattr("intentforge.review.validator._known_references", fail_live_load)
    assert validate_audit_package(package)["passed"]
