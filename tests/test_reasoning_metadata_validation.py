import yaml

from intentforge.knowledge import load_rules, validate_reasoning_metadata


def _rule(rule_id: str) -> dict:
    return {
        "id": rule_id,
        "name": "Rule",
        "category": "mechanical",
        "description": "Rule.",
        "applies_to": ["wall_mounted_bracket"],
        "condition": {"expression": "hole_spacing >= 3 * hole_diameter"},
        "severity": "warning",
        "recommendation": "Increase spacing.",
        "source_reference": "test",
        "confidence": 0.8,
    }


def test_existing_rules_without_reasoning_metadata_still_load(tmp_path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({"rules": [_rule("old_rule_001")]}), encoding="utf-8")

    rules = load_rules(path)

    assert rules[0].reasoning == {}


def test_reasoning_metadata_validation_passes_default_rules() -> None:
    result = validate_reasoning_metadata()

    assert result["ok"] is True
    assert result["rules_checked"] >= 10
    assert result["metadata_errors"] == []


def test_unknown_rule_reference_detected(tmp_path) -> None:
    bad = _rule("rule_with_bad_reference_001")
    bad["reasoning"] = {"can_conflict_with": ["missing_rule_001"]}
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({"rules": [bad]}), encoding="utf-8")

    result = validate_reasoning_metadata(path)

    assert result["ok"] is False
    assert any("unknown referenced rule id" in error["message"] for error in result["metadata_errors"])


def test_invalid_priority_weight_detected(tmp_path) -> None:
    bad = _rule("rule_with_bad_weight_001")
    bad["reasoning"] = {"priority_weight": 2}
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({"rules": [bad]}), encoding="utf-8")

    result = validate_reasoning_metadata(path)

    assert result["ok"] is False
    assert "priority_weight" in result["metadata_errors"][0]["message"]
