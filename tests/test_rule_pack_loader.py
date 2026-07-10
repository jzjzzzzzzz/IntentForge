import pytest
import yaml

from intentforge.knowledge.packs import DEFAULT_BRACKET_PACK_RESOURCES, load_default_bracket_rule_packs, load_rule_packs


def _pack(pack_id: str, rule_id: str) -> dict:
    return {
        "pack_id": pack_id,
        "pack_version": "1.0",
        "name": "Pack",
        "description": "Pack.",
        "category": "mechanical",
        "supported_model_families": ["wall_mounted_bracket"],
        "status": "active",
        "rules": [
            {
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
        ],
    }


def test_default_packs_load_in_deterministic_order() -> None:
    packs = load_default_bracket_rule_packs()

    assert [pack.source.split("/")[-1] for pack in packs] == list(DEFAULT_BRACKET_PACK_RESOURCES)
    assert [pack.pack_id for pack in packs] == [
        "bracket_mechanical",
        "bracket_manufacturing",
        "bracket_assembly",
        "bracket_structural",
    ]


def test_total_active_rule_count_remains_ten() -> None:
    packs = load_default_bracket_rule_packs()

    assert sum(len([rule for rule in pack.rules if rule.status == "active"]) for pack in packs) == 10


def test_duplicate_pack_ids_rejected(tmp_path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(yaml.safe_dump(_pack("duplicate_pack", "rule_a_001")), encoding="utf-8")
    second.write_text(yaml.safe_dump(_pack("duplicate_pack", "rule_b_001")), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate rule pack id"):
        load_rule_packs([first, second])


def test_duplicate_rule_ids_across_packs_rejected(tmp_path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(yaml.safe_dump(_pack("pack_a", "duplicate_rule_001")), encoding="utf-8")
    second.write_text(yaml.safe_dump(_pack("pack_b", "duplicate_rule_001")), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate rule id across rule packs"):
        load_rule_packs([first, second])
