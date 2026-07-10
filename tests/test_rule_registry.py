import pytest

from intentforge.knowledge import RuleRegistry, load_rules


def test_rule_registry_counts_and_categories() -> None:
    registry = RuleRegistry.load()

    assert registry.count() == len(registry.rules)
    assert registry.get_by_category("mechanical")
    assert all(rule.category == "mechanical" for rule in registry.get_by_category("mechanical"))


def test_rule_registry_active_rules() -> None:
    registry = RuleRegistry.load()

    assert registry.get_active_rules()
    assert len(registry.get_active_rules()) == registry.count()


def test_rule_registry_rejects_duplicate_ids() -> None:
    rules = load_rules()

    with pytest.raises(ValueError, match="duplicate knowledge rule id"):
        RuleRegistry([rules[0], rules[0]])
