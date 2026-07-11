import json
from pathlib import Path

from intentforge.assurance import build_audit_package, validate_audit_package
from intentforge.review import evaluate_assurance_case, get_review_policy
from tests.review_test_helpers import static_case


def test_review_decision_attachment_validates_and_changes_logical_identity(tmp_path: Path) -> None:
    case = static_case()
    policy = get_review_policy("intentforge_static_review_v1")
    decision = evaluate_assurance_case(policy, case)
    base = build_audit_package(case, tmp_path / "base")
    reviewed = build_audit_package(case, tmp_path / "reviewed", review_policy=policy, review_decision=decision)
    assert base["validation"]["passed"]
    assert reviewed["validation"]["passed"]
    assert reviewed["package_id"] != base["package_id"]
    assert reviewed["validation"]["review_decision_validation_passed"] is True


def test_old_phase23_package_remains_valid_without_review_files(tmp_path: Path) -> None:
    package = build_audit_package(static_case(), tmp_path / "base")
    assert package["validation"]["passed"]
    assert package["validation"]["review_decision_attached"] is False


def test_modified_review_decision_attachment_is_detected(tmp_path: Path) -> None:
    case = static_case()
    policy = get_review_policy("intentforge_static_review_v1")
    decision = evaluate_assurance_case(policy, case)
    root = tmp_path / "reviewed"
    build_audit_package(case, root, review_policy=policy, review_decision=decision)
    data = json.loads((root / "review_decision.json").read_text(encoding="utf-8"))
    data["decision_status"] = "rejected_by_policy"
    (root / "review_decision.json").write_text(json.dumps(data), encoding="utf-8")
    result = validate_audit_package(root)
    assert not result["passed"]
    assert result["hash_mismatch_count"] > 0
