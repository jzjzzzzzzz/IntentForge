from __future__ import annotations

import pytest
from pydantic import ValidationError

from intentforge.review.provenance_schema import FrozenDecisionSnapshot, ReviewExecutionNode


def test_frozen_snapshot_identity_is_stable() -> None:
    first = FrozenDecisionSnapshot(
        snapshot_type="decision_strategy",
        reference_id="deterministic_precedence_v1",
        version="1.0",
        payload={"rules": ["blocking", "manual", "conditional"]},
    )
    second = FrozenDecisionSnapshot.model_validate(first.model_dump(mode="json"))
    assert first.snapshot_id == second.snapshot_id
    assert first.content_id == second.content_id


def test_frozen_snapshot_rejects_tampered_payload() -> None:
    snapshot = FrozenDecisionSnapshot(
        snapshot_type="check_registry",
        reference_id="intentforge_review_check_registry",
        version="1.0",
        payload={"checks": 26},
    ).model_dump(mode="json")
    snapshot["payload"]["checks"] = 25
    with pytest.raises(ValidationError, match="snapshot content ID mismatch"):
        FrozenDecisionSnapshot.model_validate(snapshot)


def test_execution_node_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        ReviewExecutionNode(
            sequence=0,
            node_type="arbitrary_execution",
            node_key="invalid",
            status="completed",
        )


def test_execution_node_runtime_free_identity_is_stable() -> None:
    node = ReviewExecutionNode(
        sequence=4,
        node_type="check_evaluation",
        node_key="check:test",
        status="passed",
        parameters={"required": True},
        observed_value={"value": 1},
        expected_value={"value": 1},
    )
    assert ReviewExecutionNode.model_validate(node.model_dump(mode="json")).node_id == node.node_id
