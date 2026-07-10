import pytest

from intentforge.knowledge.packs import RulePackRegistry


def test_registry_counts_and_filters() -> None:
    registry = RulePackRegistry.load_default()

    assert registry.count_packs() == 4
    assert registry.count_rules() == 10
    assert registry.get_pack("bracket_mechanical").category == "mechanical"
    assert len(registry.get_by_category("mechanical")) == 1
    assert len(registry.get_for_model_family("wall_mounted_bracket")) == 4
    assert len(registry.get_for_model_family("l_bracket")) == 4


def test_registry_flattens_rules_in_pack_order() -> None:
    registry = RulePackRegistry.load_default()
    rule_ids = [rule.id for rule in registry.flatten_rules()]

    assert rule_ids[:4] == [
        "hole_edge_margin_001",
        "hole_spacing_001",
        "gusset_recommendation_001",
        "corner_radius_001",
    ]
    assert rule_ids[-2:] == ["cutout_stiffness_tradeoff_001", "thin_section_warning_001"]


def test_registry_rule_sources_are_logical() -> None:
    registry = RulePackRegistry.load_default()
    sources = registry.rule_sources()

    assert sources["hole_edge_margin_001"]["pack_id"] == "bracket_mechanical"
    assert sources["hole_edge_margin_001"]["pack_version"] == "1.0"
    assert sources["hole_edge_margin_001"]["source"] == "intentforge.knowledge.packs.data/mechanical.yaml"
    assert not sources["hole_edge_margin_001"]["source"].startswith("/")


def test_registry_duplicate_pack_handling() -> None:
    pack = RulePackRegistry.load_default().get_pack("bracket_mechanical")

    with pytest.raises(ValueError, match="duplicate rule pack id"):
        RulePackRegistry([pack, pack])
