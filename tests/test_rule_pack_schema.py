import pytest
from pydantic import ValidationError

from intentforge.knowledge.packs.schema import RulePack


def _rule(rule_id: str = "schema_rule_001", category: str = "mechanical") -> dict:
    return {
        "id": rule_id,
        "rule_version": "1.0",
        "name": "Schema Rule",
        "category": category,
        "description": "Schema rule.",
        "applies_to": ["wall_mounted_bracket"],
        "condition": {"expression": "hole_spacing >= 3 * hole_diameter"},
        "severity": "warning",
        "recommendation": "Increase spacing.",
        "source_reference": "test",
        "confidence": 0.8,
    }


def _pack(**overrides) -> dict:
    data = {
        "pack_id": "schema_pack",
        "pack_version": "1.0",
        "name": "Schema Pack",
        "description": "Schema pack.",
        "category": "mechanical",
        "supported_model_families": ["wall_mounted_bracket", "l_bracket"],
        "status": "active",
        "rules": [_rule()],
        "metadata": {},
    }
    data.update(overrides)
    return data


def test_valid_rule_pack() -> None:
    pack = RulePack.model_validate(_pack())

    assert pack.pack_id == "schema_pack"
    assert pack.pack_version == "1.0"
    assert pack.rules[0].id == "schema_rule_001"


def test_invalid_status_rejected() -> None:
    with pytest.raises(ValidationError):
        RulePack.model_validate(_pack(status="draft"))


def test_invalid_pack_id_rejected() -> None:
    with pytest.raises(ValidationError):
        RulePack.model_validate(_pack(pack_id="Random_UUID_pack"))


def test_empty_rules_rejected() -> None:
    with pytest.raises(ValidationError):
        RulePack.model_validate(_pack(rules=[]))


def test_category_mismatch_rejected() -> None:
    with pytest.raises(ValidationError):
        RulePack.model_validate(_pack(category="mechanical", rules=[_rule(category="assembly")]))


def test_supported_model_families_validated() -> None:
    with pytest.raises(ValidationError):
        RulePack.model_validate(_pack(supported_model_families=["gear"]))
