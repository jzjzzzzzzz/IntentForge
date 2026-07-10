import pytest
from pydantic import ValidationError

from intentforge.knowledge.reasoning.schema import (
    EngineeringReasoningReport,
    PrioritizedRecommendation,
    ReasoningStep,
    RuleInteraction,
)


def test_valid_reasoning_step() -> None:
    step = ReasoningStep(
        step_id="observation_001",
        step_type="observation",
        rule_ids=["hole_edge_margin_001"],
        statement="Hole edge margin warning.",
        evidence={"passed": False},
        confidence=0.9,
        sequence=1,
    )

    assert step.step_type == "observation"


def test_invalid_step_type_rejected() -> None:
    with pytest.raises(ValidationError):
        ReasoningStep(
            step_id="bad",
            step_type="invented",
            rule_ids=[],
            statement="bad",
            evidence={},
            confidence=0.5,
            sequence=1,
        )


def test_valid_rule_interaction() -> None:
    interaction = RuleInteraction(
        interaction_id="interaction_001",
        rule_ids=["hole_edge_margin_001", "hole_spacing_001"],
        interaction_type="conflicts",
        description="Rules interact.",
        effect="Review together.",
        confidence=0.8,
    )

    assert interaction.interaction_type == "conflicts"


def test_invalid_interaction_type_rejected() -> None:
    with pytest.raises(ValidationError):
        RuleInteraction(
            interaction_id="bad",
            rule_ids=["rule"],
            interaction_type="speculates",
            description="bad",
            effect="bad",
            confidence=0.5,
        )


def test_invalid_priority_rejected() -> None:
    with pytest.raises(ValidationError):
        PrioritizedRecommendation(
            recommendation_id="bad",
            rule_ids=["rule"],
            priority="urgent",
            action="Do something.",
            reason="Reason.",
            expected_effect="Effect.",
            affected_parameters=[],
            confidence=0.5,
            limitations=[],
        )


def test_report_json_serialization() -> None:
    report = EngineeringReasoningReport(
        report_id="reasoning_test",
        timestamp="2026-07-10T00:00:00+00:00",
        model_family="wall_mounted_bracket",
        source_knowledge_report_id="knowledge_test",
    )

    assert '"report_id": "reasoning_test"' in report.to_json()
