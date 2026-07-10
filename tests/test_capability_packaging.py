from importlib import resources

from intentforge.knowledge.capabilities import DEFAULT_CAPABILITY_MANIFEST_RESOURCE, load_capability_manifest
from intentforge.knowledge.rules import RuleRegistry, load_rules
from intentforge.knowledge.reasoning.verification import run_reasoning_verification


def test_capability_manifest_packaged_resource_exists() -> None:
    resource = resources.files("intentforge.knowledge.data").joinpath(DEFAULT_CAPABILITY_MANIFEST_RESOURCE)

    assert resource.is_file()
    assert "capabilities:" in resource.read_text(encoding="utf-8")


def test_capability_manifest_loads_from_package_resource() -> None:
    manifest = load_capability_manifest()

    assert manifest.capabilities
    assert manifest.capabilities[0].capability_id == "wall_basic_mounting_plate_generation"


def test_legacy_rule_loading_unchanged() -> None:
    rules = load_rules()
    registry = RuleRegistry.load()

    assert len(rules) == 10
    assert [rule.id for rule in rules] == [rule.id for rule in registry.rules]


def test_reasoning_golden_verification_unchanged() -> None:
    result = run_reasoning_verification()

    assert result["total_cases"] == 10
    assert result["failed"] == 0
    assert result["contradiction_count"] == 0
    assert result["applicability_error_count"] == 0
