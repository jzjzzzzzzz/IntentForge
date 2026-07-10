import json
from pathlib import Path

import pytest

from intentforge.cli import main
from intentforge.knowledge import load_rules


PROJECT_ROOT = Path(__file__).resolve().parents[1]


REQUIRED_RULE_IDS = {
    "hole_edge_margin_001",
    "hole_spacing_001",
    "gusset_recommendation_001",
    "corner_radius_001",
    "tool_clearance_001",
    "manufacturing_simplicity_001",
    "fastener_accessibility_001",
    "installation_difficulty_001",
    "cutout_stiffness_tradeoff_001",
    "thin_section_warning_001",
}


def test_bracket_rules_include_required_rules() -> None:
    rules = load_rules()
    rule_ids = {rule.id for rule in rules}

    assert REQUIRED_RULE_IDS <= rule_ids


def test_rules_have_explainable_recommendations() -> None:
    for rule in load_rules():
        assert rule.recommendation
        assert rule.source_reference
        assert 0.0 <= rule.confidence <= 1.0
        assert "expression" in rule.condition


def test_design_review_with_knowledge_writes_findings(capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("cadquery")

    result = main(["design-review", "l_bracket", "--knowledge"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Knowledge findings:" in output
    report_path = PROJECT_ROOT / "output" / "design_review_report.json"
    rationale_path = PROJECT_ROOT / "output" / "design_knowledge_rationale.md"
    assert report_path.exists()
    assert rationale_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["knowledge_findings"]
    assert "Design Review" in rationale_path.read_text(encoding="utf-8")
