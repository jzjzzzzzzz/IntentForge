from __future__ import annotations

from pathlib import Path

from intentforge.assurance import attach_assurance_predecessor, build_audit_package
from intentforge.review import (
    evaluate_assurance_case,
    get_review_policy,
    store_audit_package,
)
from tests.review_test_helpers import edit_case, review_resources, standard_case


def build_three_package_chain(root: Path) -> dict:
    store_root = root / "store"
    specs = (
        (standard_case(), "intentforge_standard_design_review_v1"),
        (standard_case(partial=True), "intentforge_standard_design_review_v1"),
        (edit_case(), "intentforge_edit_review_v1"),
    )
    predecessor = None
    packages = []
    stored = []
    cases = []
    decisions = []
    for index, (source_case, policy_id) in enumerate(specs):
        case = attach_assurance_predecessor(source_case, predecessor)
        policy = get_review_policy(policy_id)
        decision = evaluate_assurance_case(policy, case, resources=review_resources())
        package = build_audit_package(
            case,
            root / "packages" / str(index),
            review_policy=policy,
            review_decision=decision,
            predecessor_hash_pointer=predecessor,
        )
        stored_result = store_audit_package(package["package_path"], store_root)
        assert stored_result.passed
        predecessor = stored_result.content_address
        packages.append(Path(package["package_path"]))
        stored.append(Path(stored_result.storage_path))
        cases.append(case)
        decisions.append(decision)
    return {
        "store_root": store_root,
        "packages": packages,
        "stored": stored,
        "cases": cases,
        "decisions": decisions,
        "addresses": [item.name for item in stored],
        "content_addresses": ["sha256:" + item.name for item in stored],
    }
