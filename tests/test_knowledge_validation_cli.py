import json

import yaml

from intentforge.cli import main
from intentforge.knowledge import validate_rule_data


def _minimal_rule(rule_id: str) -> dict:
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


def test_validate_rule_data_passes_default_rules() -> None:
    result = validate_rule_data()

    assert result["ok"] is True
    assert result["rules_checked"] >= 10
    assert result["errors"] == []


def test_validate_rule_data_detects_duplicates(tmp_path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({"rules": [_minimal_rule("dup_rule_001"), _minimal_rule("dup_rule_001")]}), encoding="utf-8")

    result = validate_rule_data(path)

    assert result["ok"] is False
    assert any("duplicate rule id" in error["message"] for error in result["errors"])


def test_validate_rule_data_detects_invalid_status(tmp_path) -> None:
    rule = _minimal_rule("bad_status_rule_001")
    rule["status"] = "draft"
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump({"rules": [rule]}), encoding="utf-8")

    result = validate_rule_data(path)

    assert result["ok"] is False
    assert any(error.get("field") == "status" for error in result["errors"])


def test_knowledge_validate_cli(capsys) -> None:
    result = main(["knowledge", "validate"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Knowledge validation" in output
    assert "PASS" in output
    assert "0 errors" in output


def test_design_review_knowledge_json_export(capsys) -> None:
    import pytest

    pytest.importorskip("cadquery")

    result = main(["design-review", "wall_mounted_bracket", "--knowledge", "--json"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Knowledge JSON report:" in output
    with open("output/knowledge_report.json", encoding="utf-8") as report_file:
        report = json.load(report_file)
    assert report["rules_checked"] >= 10
    assert report["findings"]
