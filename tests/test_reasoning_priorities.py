from intentforge.knowledge.reasoning.priorities import priority_from_score, score_finding
from reasoning_test_helpers import finding, registry


def test_higher_severity_ranks_above_informational() -> None:
    reg = registry()
    warning = finding("hole_edge_margin_001", passed=False)
    info = warning.model_copy(update={"severity": "info", "confidence": 0.9})

    assert score_finding(warning, reg.get("hole_edge_margin_001")) > score_finding(info, reg.get("hole_edge_margin_001"))


def test_priority_mapping_is_stable() -> None:
    assert priority_from_score(150) == "critical"
    assert priority_from_score(100) == "high"
    assert priority_from_score(60) == "medium"
    assert priority_from_score(30) == "low"
    assert priority_from_score(5) == "informational"


def test_reinforcing_findings_increase_priority_score() -> None:
    from intentforge.knowledge.reasoning.schema import RuleInteraction

    reg = registry()
    item = finding("thin_section_warning_001", passed=False)
    base = score_finding(item, reg.get("thin_section_warning_001"))
    reinforced = score_finding(
        item,
        reg.get("thin_section_warning_001"),
        [
            RuleInteraction(
                interaction_id="interaction_test",
                rule_ids=["thin_section_warning_001", "cutout_stiffness_tradeoff_001"],
                interaction_type="reinforces",
                description="reinforces",
                effect="increase priority",
                confidence=0.7,
            )
        ],
    )

    assert reinforced > base
