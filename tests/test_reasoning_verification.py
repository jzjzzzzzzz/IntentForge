from intentforge.knowledge import RuleRegistry
from intentforge.knowledge.reasoning.schema import PrioritizedRecommendation
from intentforge.knowledge.reasoning.verification import (
    detect_recommendation_contradictions,
    validate_recommendation_applicability,
)
from reasoning_test_helpers import reasoning_report


def _recommendation(action: str, parameter: str, recommendation_id: str) -> PrioritizedRecommendation:
    return PrioritizedRecommendation(
        recommendation_id=recommendation_id,
        rule_ids=["hole_edge_margin_001"],
        priority="high",
        action=action,
        reason="test",
        expected_effect="test",
        affected_parameters=[parameter],
        confidence=0.9,
        limitations=["test limitation"],
    )


def test_contradiction_detection_catches_direct_opposite_parameter_actions() -> None:
    contradictions = detect_recommendation_contradictions(
        [
            _recommendation("Increase plate width.", "plate_width", "rec_001"),
            _recommendation("Reduce plate width.", "plate_width", "rec_002"),
        ]
    )

    assert contradictions
    assert contradictions[0]["affected_parameters"] == ["plate_width"]


def test_contradiction_detection_avoids_indirect_cutout_false_positive() -> None:
    report = reasoning_report(["cutout_stiffness_tradeoff_001", "thin_section_warning_001"])

    assert detect_recommendation_contradictions(report.recommendations) == []


def test_applicability_validation_passes_real_report() -> None:
    report = reasoning_report(["hole_edge_margin_001"])

    assert validate_recommendation_applicability(report, RuleRegistry.load()) == []


def test_applicability_validation_rejects_unknown_parameter() -> None:
    report = reasoning_report(["hole_edge_margin_001"])
    bad_recommendation = report.recommendations[0].model_copy(
        update={"affected_parameters": ["unsupported_parameter"]}
    )
    bad_report = report.model_copy(update={"recommendations": [bad_recommendation]})

    issues = validate_recommendation_applicability(bad_report, RuleRegistry.load())

    assert issues
    assert issues[0]["affected_parameters"] == ["unsupported_parameter"]
