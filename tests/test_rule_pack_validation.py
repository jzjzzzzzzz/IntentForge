import pytest
from pydantic import ValidationError

from intentforge.knowledge.packs import RulePack, validate_default_rule_packs, validate_rule_packs


def _rule(rule_id: str, *, reference: str | None = None, confidence: float = 0.8) -> dict:
    reasoning = {}
    if reference:
        reasoning = {"can_conflict_with": [reference]}
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
        "confidence": confidence,
        "reasoning": reasoning,
    }


def _pack(rules: list[dict], *, status: str = "active") -> RulePack:
    return RulePack.model_validate(
        {
            "pack_id": "validation_pack",
            "pack_version": "1.0",
            "name": "Validation Pack",
            "description": "Validation pack.",
            "category": "mechanical",
            "supported_model_families": ["wall_mounted_bracket"],
            "status": status,
            "rules": rules,
            "metadata": {},
        }
    )


def test_valid_default_packs_pass() -> None:
    result = validate_default_rule_packs()

    assert result.passed is True
    assert result.packs_checked == 4
    assert result.rules_checked == 10
    assert result.summary["active_rule_count"] == 10


def test_unknown_rule_reference_fails() -> None:
    pack = _pack([_rule("known_rule_001", reference="missing_rule_001")])
    result = validate_rule_packs([pack])

    assert result.passed is False
    assert result.summary["unknown_rule_reference_count"] == 1
    assert any("unknown referenced rule id" in error["message"] for error in result.errors)


def test_invalid_confidence_fails_schema() -> None:
    with pytest.raises(ValidationError):
        _pack([_rule("bad_confidence_001", confidence=1.5)])


def test_deprecated_pack_warns_but_validates() -> None:
    pack = _pack([_rule("deprecated_rule_001")], status="deprecated")
    result = validate_rule_packs([pack])

    assert result.passed is True
    assert result.summary["deprecated_pack_count"] == 1
    assert result.warnings
