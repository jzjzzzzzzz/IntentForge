from intentforge.cli import main
from intentforge.knowledge import RuleRegistry, load_rules


def test_default_rules_load() -> None:
    rules = load_rules()

    assert len(rules) >= 10
    assert all(rule.id for rule in rules)
    assert {rule.category for rule in rules} >= {"mechanical", "manufacturing", "assembly", "structural"}


def test_rule_registry_filters_by_family() -> None:
    registry = RuleRegistry.load()

    wall_rules = registry.for_family("wall_mounted_bracket")
    l_rules = registry.for_family("l_bracket")

    assert len(registry) >= 10
    assert wall_rules
    assert l_rules


def test_knowledge_list_cli(capsys) -> None:
    result = main(["knowledge", "list"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Engineering Knowledge Rules" in output
    assert "Total:" in output
    assert "Mechanical:" in output
