from __future__ import annotations

from pathlib import Path

from intentforge.assurance import build_audit_package
from intentforge.review import evaluate_assurance_case, get_review_policy
from tests.review_test_helpers import review_resources, static_case


def build_portable_review_package(
    root: Path,
    *,
    case=None,
    policy_id: str = "intentforge_static_review_v1",
) -> Path:
    record = case or static_case()
    policy = get_review_policy(policy_id)
    decision = evaluate_assurance_case(policy, record, resources=review_resources())
    result = build_audit_package(
        record,
        root,
        review_policy=policy,
        review_decision=decision,
    )
    assert result["validation"]["passed"]
    return root
