from intentforge.knowledge import generate_design_rationale
from intentforge.knowledge.schema import KnowledgeFinding


def test_rationale_generation_includes_warning_and_recommendation() -> None:
    finding = KnowledgeFinding(
        rule_id="hole_edge_margin_001",
        rule_name="Hole Edge Margin",
        category="mechanical",
        severity="warning",
        passed=False,
        message="The hole is too close to the edge.",
        recommendation="Increase hole edge distance.",
        confidence=0.9,
        metadata={"expression": "hole_edge_distance >= 1.5 * hole_diameter"},
    )

    rationale = generate_design_rationale([finding])

    assert "# Design Review" in rationale
    assert "WARNING: Hole Edge Margin" in rationale
    assert "Increase hole edge distance." in rationale
    assert "does not represent FEA" in rationale


def test_rationale_generation_handles_no_findings() -> None:
    rationale = generate_design_rationale([])

    assert "No applicable engineering knowledge findings" in rationale
