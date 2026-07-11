from __future__ import annotations

from intentforge.review import evaluate_assurance_case, get_review_policy, verify_decision_provenance
from tests.review_test_helpers import rejection_case, review_resources, standard_case


def _decision():
    return evaluate_assurance_case(
        get_review_policy("intentforge_standard_design_review_v1"),
        standard_case(),
        resources=review_resources(),
    )


def test_frozen_replay_reproduces_decision_and_provenance_ids() -> None:
    decision = _decision()
    result = verify_decision_provenance(decision, perform_replay=True)
    assert result.passed
    assert result.status == "verified"
    assert result.replay_decision_id == decision.decision_id
    assert result.replay_mismatch_count == 0


def test_replay_does_not_reload_live_rule_capability_or_evidence_registries(monkeypatch) -> None:
    decision = _decision()

    def fail_live_load(*args, **kwargs):
        raise AssertionError("live registry must not be used during frozen replay")

    monkeypatch.setattr("intentforge.assurance.validator.load_capability_manifest", fail_live_load)
    monkeypatch.setattr("intentforge.assurance.validator.load_evidence_definitions", fail_live_load)
    monkeypatch.setattr("intentforge.assurance.validator.RuleRegistry.load", fail_live_load)
    monkeypatch.setattr("intentforge.review.checks.load_evidence_definitions", fail_live_load)
    assert verify_decision_provenance(decision, perform_replay=True).passed


def test_incompatible_engine_contract_is_not_silently_replayed() -> None:
    decision = _decision()
    assert decision.decision_provenance is not None
    incompatible = decision.model_copy(update={
        "decision_provenance": decision.decision_provenance.model_copy(update={"evaluator_version": "2.0"})
    })
    result = verify_decision_provenance(incompatible, perform_replay=True)
    assert not result.passed
    assert result.status == "unsupported"
    assert not result.replay_performed


def test_static_verification_does_not_claim_runtime_replay() -> None:
    result = verify_decision_provenance(_decision(), perform_replay=False)
    assert result.passed
    assert not result.replay_performed


def test_safe_rejection_replay_preserves_no_cad_boundary() -> None:
    decision = evaluate_assurance_case(
        get_review_policy("intentforge_safe_rejection_review_v1"),
        rejection_case(),
        resources=review_resources(),
    )
    assert decision.decision_status == "accepted_within_declared_scope"
    assert decision.subject_type == "safe_rejection"
    assert decision.decision_provenance is not None
    artifacts = decision.decision_provenance.active_boundary_conditions["artifacts"]
    assert artifacts == {}
    assert verify_decision_provenance(decision, perform_replay=True).passed
