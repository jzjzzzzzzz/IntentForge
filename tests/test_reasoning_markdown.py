from intentforge.knowledge.reasoning.templates import render_engineering_reasoning_markdown
from reasoning_test_helpers import reasoning_report


def test_markdown_includes_rule_versions_confidence_and_limitations() -> None:
    report = reasoning_report(["hole_edge_margin_001"])
    markdown = render_engineering_reasoning_markdown(report)

    assert "# Engineering Reasoning Report" in markdown
    assert "hole_edge_margin_001 v1.0" in markdown
    assert "Confidence:" in markdown
    assert "does not replace load-specific engineering analysis" in markdown


def test_markdown_avoids_simulation_claims() -> None:
    report = reasoning_report(["hole_edge_margin_001"])
    markdown = render_engineering_reasoning_markdown(report).lower()

    assert "fea result" not in markdown
    assert "certifies" not in markdown
