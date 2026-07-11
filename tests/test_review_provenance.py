from __future__ import annotations

from intentforge.review import evaluate_assurance_case, get_review_policy
from intentforge.assurance.schema import canonical_digest
from intentforge.review.schema import ReviewDecision
from intentforge.review.validator import validate_review_decision
from tests.review_test_helpers import review_resources, static_case


def _decision():
    return evaluate_assurance_case(
        get_review_policy("intentforge_static_review_v1"),
        static_case(),
        resources=review_resources(),
    )


def test_decision_freezes_complete_review_runtime_chain() -> None:
    decision = _decision()
    provenance = decision.decision_provenance
    assert provenance is not None
    assert {item.snapshot_type for item in provenance.snapshots} == {
        "review_policy",
        "assurance_case",
        "rule_registry",
        "capability_registry",
        "evidence_registry",
        "evidence_resolution",
        "check_registry",
        "decision_strategy",
        "audit_package_observation",
        "boundary_conditions",
    }
    assert provenance.evidence_definition_count == 65
    assert provenance.evidence_observation_count == 65
    assert len(provenance.snapshot("rule_registry").payload["rules"]) == 10
    assert len(provenance.snapshot("capability_registry").payload["capabilities"]) == 28


def test_execution_chain_records_every_policy_check_and_parameter_set() -> None:
    decision = _decision()
    provenance = decision.decision_provenance
    assert provenance is not None
    policy = get_review_policy("intentforge_static_review_v1")
    check_nodes = [item for item in provenance.execution_nodes if item.node_type == "check_evaluation"]
    assert [item.check_id for item in check_nodes] == sorted(item.check_id for item in policy.checks)
    assert all(item.parameters == next(check.parameters.model_dump(mode="json") for check in policy.checks if check.check_id == item.check_id) for item in check_nodes)
    assert [item.sequence for item in provenance.execution_nodes] == list(range(len(provenance.execution_nodes)))


def test_boundary_conditions_are_explicit_and_family_scoped() -> None:
    provenance = _decision().decision_provenance
    assert provenance is not None
    boundary = provenance.active_boundary_conditions
    assert boundary["cad_family"] == "wall_mounted_bracket"
    assert boundary["subject_type"] == "design_result"
    assert boundary["assurance_profile"] == "static"
    assert "claim_statuses" in boundary
    assert "validation_statuses" in boundary


def test_runtime_metadata_does_not_change_provenance_identity() -> None:
    policy = get_review_policy("intentforge_static_review_v1")
    first = evaluate_assurance_case(
        policy, static_case(), resources=review_resources(), runtime_metadata={"timestamp": "one"}
    )
    second = evaluate_assurance_case(
        policy, static_case(), resources=review_resources(), runtime_metadata={"timestamp": "two"}
    )
    assert first.decision_provenance is not None
    assert second.decision_provenance is not None
    assert first.decision_provenance.provenance_id == second.decision_provenance.provenance_id
    assert first.decision_id == second.decision_id


def test_legacy_phase24_decision_without_provenance_remains_valid() -> None:
    decision = _decision().model_copy(update={"decision_provenance": None})
    content_id = canonical_digest("review_decision_content", decision.deterministic_payload())
    legacy = decision.model_copy(update={
        "content_id": content_id,
        "decision_id": canonical_digest("review_decision", {"content_id": content_id}),
    })
    payload = legacy.model_dump(mode="json")
    payload.pop("decision_provenance", None)
    loaded = ReviewDecision.model_validate(payload)
    assert loaded.decision_provenance is None
    assert validate_review_decision(
        loaded,
        policy=get_review_policy("intentforge_static_review_v1"),
        assurance_case=static_case(),
    ).passed
