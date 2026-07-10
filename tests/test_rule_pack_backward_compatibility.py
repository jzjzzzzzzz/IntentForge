from intentforge.cli import main
from intentforge.knowledge import RulePackRegistry, RuleRegistry, load_rules, validate_rule_data


def test_legacy_bracket_rules_manifest_loads_same_rules() -> None:
    pack_registry = RulePackRegistry.load_default()
    legacy_rules = load_rules()

    assert [rule.id for rule in legacy_rules] == [rule.id for rule in pack_registry.flatten_rules()]
    assert len(legacy_rules) == 10


def test_rule_registry_legacy_load_keeps_source_map() -> None:
    registry = RuleRegistry.load()
    sources = registry.rule_sources()

    assert registry.count() == 10
    assert sources["hole_spacing_001"]["pack_id"] == "bracket_mechanical"


def test_legacy_validate_rule_data_delegates_to_pack_validation() -> None:
    result = validate_rule_data()

    assert result["ok"] is True
    assert result["rules_checked"] == 10
    assert result["errors"] == []
    assert result["pack_validation"]["summary"]["active_pack_count"] == 4


def test_existing_knowledge_commands_still_work(capsys) -> None:
    assert main(["knowledge", "list"]) == 0
    assert main(["knowledge", "validate"]) == 0
    assert main(["knowledge", "reasoning-verify"]) == 0
    output = capsys.readouterr().out
    assert "Engineering Knowledge Rules" in output
    assert "Knowledge validation" in output
    assert "Engineering reasoning verification" in output
