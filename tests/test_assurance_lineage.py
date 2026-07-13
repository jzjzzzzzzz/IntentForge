from __future__ import annotations

import pytest

from intentforge.assurance import attach_assurance_predecessor, validate_assurance_case
from intentforge.review import evaluate_assurance_case, get_review_policy, verify_decision_provenance
from tests.review_test_helpers import review_resources, static_case


PREDECESSOR = "sha256:" + "1" * 64


def test_assurance_predecessor_is_bound_to_claims_and_arguments() -> None:
    source = static_case()
    bound = attach_assurance_predecessor(source, PREDECESSOR)
    assert source.predecessor_hash_pointer is None
    assert bound.predecessor_hash_pointer == PREDECESSOR
    assert all(item.predecessor_hash_pointer == PREDECESSOR for item in bound.claims)
    assert all(item.predecessor_hash_pointer == PREDECESSOR for item in bound.arguments)
    assert bound.assurance_case_id != source.assurance_case_id
    assert validate_assurance_case(bound).passed


def test_assurance_lineage_identity_is_deterministic() -> None:
    source = static_case()
    first = attach_assurance_predecessor(source, PREDECESSOR)
    second = attach_assurance_predecessor(source, PREDECESSOR)
    assert first.assurance_case_id == second.assurance_case_id
    assert [item.claim_id for item in first.claims] == [item.claim_id for item in second.claims]
    assert [item.argument_id for item in first.arguments] == [item.argument_id for item in second.arguments]


def test_conflicting_or_malformed_predecessor_is_rejected() -> None:
    source = attach_assurance_predecessor(static_case(), PREDECESSOR)
    with pytest.raises(ValueError):
        attach_assurance_predecessor(source, "sha256:" + "2" * 64)
    with pytest.raises(ValueError):
        attach_assurance_predecessor(static_case(), "not-a-hash")


def test_review_provenance_records_lineage_snapshot_and_node() -> None:
    case = attach_assurance_predecessor(static_case(), PREDECESSOR)
    decision = evaluate_assurance_case(
        get_review_policy("intentforge_static_review_v1"),
        case,
        resources=review_resources(),
    )
    assert decision.predecessor_hash_pointer == PREDECESSOR
    assert decision.decision_provenance is not None
    assert decision.decision_provenance.predecessor_hash_pointer == PREDECESSOR
    assert decision.decision_provenance.snapshot("audit_lineage").payload["predecessor_hash_pointer"] == PREDECESSOR
    assert any(item.node_type == "lineage_binding" for item in decision.decision_provenance.execution_nodes)
    assert verify_decision_provenance(decision, perform_replay=True).passed


def test_genesis_decision_keeps_legacy_provenance_shape() -> None:
    decision = evaluate_assurance_case(
        get_review_policy("intentforge_static_review_v1"),
        static_case(),
        resources=review_resources(),
    )
    assert decision.predecessor_hash_pointer is None
    assert decision.decision_provenance is not None
    assert len(decision.decision_provenance.snapshots) == 10
    assert len(decision.decision_provenance.execution_nodes) == 14
