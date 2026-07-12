"""Phase 28: Deterministic semantic pruning engine tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from intentforge.redaction.config import (
    RedactionConfig,
    RedactionFieldSelector,
    RedactionRule,
    default_redaction_config,
    load_redaction_config,
)
from intentforge.redaction.engine import (
    PruningResult,
    RedactionResult,
    SemanticPruner,
    prune_document,
    prune_json_file,
)


def test_redaction_rule_matches_numeric_geometry_field() -> None:
    config = default_redaction_config()
    rule = config.rules[0]
    assert rule.matches("$.parameters[0].width", "width", 120)
    assert rule.matches("$.height", "height", 60.5)
    assert not rule.matches("$.width", "status", 120)


def test_redaction_rule_preserves_id_fields() -> None:
    config = default_redaction_config()
    path = "$.claim_id"
    field_name = "claim_id"
    assert config.should_protect(path)
    assert config.should_redact(path, field_name, 12345) is None


def test_default_redaction_handles_nested_parameters() -> None:
    document = {
        "parameters": [
            {"name": "width", "value": 120},
            {"name": "height", "value": 60},
            {"name": "thickness", "value": 8},
        ],
        "metadata": {"width": 100, "height": 50},
        "claim_id": "claim_abc123",
        "decision_status": "accepted_within_declared_scope",
    }
    result = prune_document(document)
    assert result.passed
    assert result.metrics["total_redactions"] >= 4
    assert result.redacted_document["parameters"][0]["value"] == "[REDACTED_GEOMETRY_VALUE]"
    assert result.redacted_document["parameters"][1]["value"] == "[REDACTED_GEOMETRY_VALUE]"
    assert result.redacted_document["metadata"]["width"] == "[REDACTED_GEOMETRY_VALUE]"
    assert result.redacted_document["claim_id"] == "claim_abc123"
    assert result.redacted_document["decision_status"] == "accepted_within_declared_scope"


def test_pruning_is_deterministic() -> None:
    document = {
        "parameters": [{"name": "width", "value": 100}],
        "constraints": [{"name": "max_height", "value": 200}],
    }
    config = default_redaction_config()
    result1 = prune_document(document, config)
    result2 = prune_document(document, config)
    assert json.dumps(result1.redacted_document, sort_keys=True) == json.dumps(result2.redacted_document, sort_keys=True)


def test_redaction_produces_structured_tokens() -> None:
    document = {
        "parameters": [
            {"name": "width", "value": 120},
            {"name": "thickness", "value": 8.5},
        ],
        "metadata": {"position_offset": 25.5, "material": "A36 steel"},
    }
    config = default_redaction_config()
    result = prune_document(document, config)
    assert result.redacted_document["parameters"][0]["value"] == "[REDACTED_GEOMETRY_VALUE]"
    assert result.redacted_document["parameters"][1]["value"] == "[REDACTED_GEOMETRY_VALUE]"
    assert result.redacted_document["metadata"]["position_offset"] == "[REDACTED_POSITION_VALUE]"
    assert result.redacted_document["metadata"]["material"] == "[REDACTED_MATERIAL_VALUE]"


def test_redaction_path_is_recorded() -> None:
    document = {"parameters": [{"width": 100}]}
    config = default_redaction_config()
    result = prune_document(document, config)
    paths = {r.path for r in result.redactions}
    assert any("$.parameters" in p and ".width" in p for p in paths), f"paths: {paths}"


def test_custom_redaction_rule() -> None:
    config = RedactionConfig(
        description="Custom config for temperature",
        rules=[
            RedactionRule(
                name="temperature",
                description="Redact temperature values",
                severity="high",
                selectors=[{"field_name_pattern": r"^(temperature|temp)$", "value_type": "numeric"}],
                token_type="redacted_hash",
                salt="custom-salt",
            ),
        ],
    )
    document = {"temperature": 850.5, "metadata": {"temp": 25.0}}
    result = prune_document(document, config)
    assert result.redacted_document["temperature"].startswith("[REDACTED_HASH_")
    assert len(result.redacted_document["temperature"]) == len("[REDACTED_HASH_") + 16 + 1


def test_structural_redaction_inventory() -> None:
    document = {
        "claim_id": "abc",
        "parameters": [{"name": "width", "value": 120}, {"name": "depth", "value": 8}],
        "constraints": [{"name": "min_thickness", "value": 3}],
    }
    result = prune_document(document)
    assert "claim_id" not in {r.field_name for r in result.redactions}
    assert "value" in {r.field_name for r in result.redactions}


def test_pruning_preserves_list_structures() -> None:
    document = {
        "findings": [
            {"claim_id": "c1", "claim_ids": ["a"], "data": {"width": 120}},
            {"claim_id": "c2", "claim_ids": ["b"], "data": {"height": 60}},
        ],
    }
    result = prune_document(document)
    assert len(result.redacted_document["findings"]) == 2
    assert result.redacted_document["findings"][0]["data"]["width"] == "[REDACTED_GEOMETRY_VALUE]"


def test_prune_json_file_writes_redacted_output(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.json"
    document = {"parameters": [{"name": "width", "value": 120}], "claim_id": "abc123"}
    input_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    result = prune_json_file(input_path, output_path)
    assert result.passed
    assert output_path.exists()
    redacted = json.loads(output_path.read_text(encoding="utf-8"))
    assert redacted["parameters"][0]["value"] == "[REDACTED_GEOMETRY_VALUE]"
    assert redacted["claim_id"] == "abc123"


def test_redacted_geometry_token_is_constant() -> None:
    document = {"width": 100}
    config = default_redaction_config()
    result1 = prune_document(document, config)
    result2 = prune_document(document, config)
    assert result1.redacted_document["width"] == result2.redacted_document["width"] == "[REDACTED_GEOMETRY_VALUE]"


def test_redaction_complex_document_full_coverage() -> None:
    document = {
        "parameters": [
            {"name": "width", "value": 120},
            {"name": "height", "value": 60},
            {"name": "thickness", "value": 8},
        ],
        "metadata": {
            "width": 100,
            "x_pos": 50,
            "y_pos": 30,
            "radius": 5.0,
            "material": "Steel",
        },
        "claim_id": "claim_xyz",
        "operation": "design_result",
        "decision_status": "accepted_within_declared_scope",
    }
    result = prune_document(document)
    redacted = result.redacted_document

    assert redacted["parameters"][0]["value"] == "[REDACTED_GEOMETRY_VALUE]"
    assert redacted["metadata"]["width"] == "[REDACTED_GEOMETRY_VALUE]"
    assert redacted["metadata"]["radius"] == "[REDACTED_GEOMETRY_VALUE]"
    assert redacted["metadata"]["x_pos"] == "[REDACTED_POSITION_VALUE]"
    assert redacted["metadata"]["y_pos"] == "[REDACTED_POSITION_VALUE]"
    assert redacted["metadata"]["material"] == "[REDACTED_MATERIAL_VALUE]"
    assert redacted["claim_id"] == "claim_xyz"
    assert redacted["operation"] == "design_result"
    assert redacted["decision_status"] == "accepted_within_declared_scope"


def test_load_redaction_config_from_json(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_data = {
        "schema_version": "1.0",
        "description": "Test config",
        "rules": [
            {
                "name": "test_rule",
                "description": "Test",
                "severity": "high",
                "selectors": [{"field_name_pattern": r"^test$"}],
                "token_type": "redacted_geometry",
            }
        ],
    }
    config_file.write_text(json.dumps(config_data, indent=2) + "\n", encoding="utf-8")
    config = load_redaction_config(config_file)
    assert config.rules[0].name == "test_rule"
