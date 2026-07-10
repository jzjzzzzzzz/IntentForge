import yaml

from intentforge.knowledge import load_rules
from intentforge.knowledge.schema import DesignKnowledgeRule


def test_old_yaml_rule_uses_safe_metadata_defaults() -> None:
    rule = DesignKnowledgeRule(
        id="old_rule_001",
        name="Old Rule",
        category="mechanical",
        description="Legacy rule without lifecycle metadata.",
        applies_to=["wall_mounted_bracket"],
        condition={"expression": "hole_spacing >= 3 * hole_diameter"},
        severity="warning",
        recommendation="Increase spacing.",
        source_reference="legacy",
        confidence=0.8,
    )

    assert rule.rule_version == "1.0"
    assert rule.status == "active"
    assert rule.created_by == "intentforge-team"
    assert rule.last_updated == "2026-07-10"


def test_rule_metadata_loads_from_yaml(tmp_path) -> None:
    rule_path = tmp_path / "rules.yaml"
    rule_path.write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {
                        "id": "metadata_rule_001",
                        "rule_version": "2.1",
                        "status": "deprecated",
                        "created_by": "test-team",
                        "last_updated": "2026-07-10",
                        "name": "Metadata Rule",
                        "category": "mechanical",
                        "description": "Rule with metadata.",
                        "applies_to": ["wall_mounted_bracket"],
                        "condition": {"expression": "hole_spacing >= 3 * hole_diameter"},
                        "severity": "warning",
                        "recommendation": "Revise.",
                        "source_reference": "test",
                        "confidence": 0.7,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    rule = load_rules(rule_path)[0]

    assert rule.rule_version == "2.1"
    assert rule.status == "deprecated"
    assert rule.created_by == "test-team"


def test_default_rules_have_stable_ids_and_versions() -> None:
    for rule in load_rules():
        assert rule.id.endswith("_001")
        assert rule.rule_version == "1.0"
        assert rule.status == "active"
