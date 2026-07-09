from pathlib import Path

import pytest

from intentforge.llm import (
    MockLLMProvider,
    translate_edit_apply,
    translate_edit_to_request,
    translate_prompt_to_build,
    translate_prompt_to_intent,
)
from intentforge.llm.provider import OpenAICompatibleProvider
from intentforge.llm.schema_guard import LLMSchemaGuardError, validate_intent_translation
from intentforge.cli import main
from mcp_server import tools


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def test_wall_bracket_prompt_translates_to_valid_intent() -> None:
    provider = MockLLMProvider()

    result = translate_prompt_to_intent(
        "Make a wall-mounted bracket 120 mm wide with two screw holes.",
        provider,
        request_id="req_llm_wall",
    )

    assert result["ok"] is True
    assert result["request_id"] == "req_llm_wall"
    assert result["operation"] == "llm_parse"
    assert result["object_type"] == "wall_mounted_bracket"
    assert result["parameters"]["family"] == "wall_mounted_bracket"
    assert "mounting_holes" in result["active_features"]


def test_l_bracket_prompt_translates_to_valid_intent() -> None:
    provider = MockLLMProvider()

    result = translate_prompt_to_intent(
        "Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, and 6 mm thick.",
        provider,
    )

    assert result["ok"] is True
    assert result["object_type"] == "l_bracket"
    assert result["parameters"]["family"] == "l_bracket"


def test_width_edit_translates_to_set_parameter() -> None:
    provider = MockLLMProvider()

    result = translate_edit_to_request(
        "Make it 150 mm wide but keep the same thickness.",
        "wall_mounted_bracket",
        provider,
    )

    assert result["ok"] is True
    assert result["operation"] == "llm_edit_parse"
    assert result["edit_request"]["edits"][0]["type"] == "set_parameter"
    assert result["edit_request"]["edits"][0]["parameter"] == "width"
    assert "thickness" in result["edit_request"]["preserve"]


def test_add_gusset_edit_translates_to_enable_feature() -> None:
    provider = MockLLMProvider()

    result = translate_edit_to_request("Add a triangular gusset.", "l_bracket", provider)

    assert result["ok"] is True
    assert result["edit_request"]["edits"][0]["type"] == "enable_feature"
    assert result["edit_request"]["edits"][0]["feature"] == "triangular_gusset"


@pytest.mark.parametrize(
    "prompt, expected",
    [
        ("Make a gear with 24 teeth.", "Unsupported object"),
        ("Make an enclosure.", "Unsupported object"),
        ("Make a curved L-bracket.", "Unsupported geometry"),
        ("Add freeform holes at arbitrary coordinates.", "Unsupported geometry"),
    ],
)
def test_guardrail_prompt_rejections(prompt: str, expected: str) -> None:
    provider = MockLLMProvider()

    result = translate_prompt_to_intent(prompt, provider)

    assert result["ok"] is False
    assert expected in result["error"]["message"]
    assert result["artifacts"] == []


def test_three_hole_edit_rejected() -> None:
    provider = MockLLMProvider()

    result = translate_edit_to_request("Add three holes.", "wall_mounted_bracket", provider)

    assert result["ok"] is False
    assert "hole" in result["error"]["message"].lower()


def test_vague_edit_rejected() -> None:
    provider = MockLLMProvider()

    result = translate_edit_to_request("Make it better.", "wall_mounted_bracket", provider)

    assert result["ok"] is False
    assert "ambiguous" in result["error"]["message"].lower()


def test_contract_success_and_failure_shapes() -> None:
    provider = MockLLMProvider()
    success = translate_prompt_to_intent(
        "Make a wall-mounted bracket 120 mm wide with two screw holes.",
        provider,
    )
    failure = translate_prompt_to_intent("Make a gear with 24 teeth.", provider)

    assert success["ok"] is True
    assert success["request_id"]
    assert success["operation"] == "llm_parse"
    assert failure["ok"] is False
    assert failure["error"]["message"]
    assert failure["cad_exported"] is False


def test_dry_run_llm_parse_build_does_not_export_step_or_stl(tmp_path: Path) -> None:
    _require_cadquery()
    provider = MockLLMProvider()

    result = translate_prompt_to_build(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes.",
        provider,
        tmp_path,
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["cad_exported"] is False
    assert not (tmp_path / "parsed_bracket.step").exists()
    assert not (tmp_path / "parsed_bracket.stl").exists()


def test_llm_edit_apply_dry_run_does_not_export_step_or_stl(tmp_path: Path) -> None:
    _require_cadquery()
    provider = MockLLMProvider()

    result = translate_edit_apply(
        "Make it 150 mm wide but keep the same thickness.",
        "wall_mounted_bracket",
        provider,
        tmp_path,
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["accepted"] is True
    assert result["cad_exported"] is False
    assert not (tmp_path / "bracket_edited.step").exists()


def test_llm_commands_do_not_call_real_network_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(OpenAICompatibleProvider, "complete_json", fail_network)
    provider = MockLLMProvider()

    result = translate_prompt_to_intent("Make a wall-mounted bracket with two screw holes.", provider)

    assert result["ok"] is True


def test_cli_llm_parse_with_mock_provider_runs() -> None:
    result = main(["llm-parse", "Make a wall-mounted bracket 120 mm wide with two screw holes.", "--mock-provider"])

    assert result == 0


def test_cli_llm_parse_without_provider_returns_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("INTENTFORGE_CONFIG_PATH", str(tmp_path / "missing.json"))
    monkeypatch.delenv("INTENTFORGE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("INTENTFORGE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = main(["llm-parse", "Make a wall-mounted bracket 120 mm wide with two screw holes."])

    assert result == 1


def test_mcp_llm_parse_build_provider_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("INTENTFORGE_CONFIG_PATH", str(tmp_path / "missing.json"))
    monkeypatch.delenv("INTENTFORGE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("INTENTFORGE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = tools.llm_parse_build_cad_prompt("Make a wall-mounted bracket with two screw holes.")

    assert result["ok"] is False
    assert result["error"]["error_type"] == "LLMProviderUnavailableError"


def test_mcp_llm_parse_build_with_mock_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _require_cadquery()
    monkeypatch.setenv("INTENTFORGE_LLM_PROVIDER", "mock")

    result = tools.llm_parse_build_cad_prompt(
        "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes.",
        output_root=str(tmp_path),
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["operation"] == "llm_parse_build"
    assert result["cad_exported"] is False


def test_schema_guard_rejects_invalid_feature_state() -> None:
    with pytest.raises(LLMSchemaGuardError, match="unsupported state"):
        validate_intent_translation(
            {
                "object_type": "wall_mounted_bracket",
                "units": "mm",
                "parameters": {"width": 120},
                "feature_flags": {
                    "mounting_holes": {"state": "maybe", "reason": "bad"}
                },
                "assumptions": [],
                "unknowns": [],
                "warnings": [],
            },
            "Make a wall-mounted bracket.",
        )


# ── Provider compatibility tests ────────────────────────────────────


class TestOpenAICompatibleProviderRoleMapping:
    """Verify that the OpenAI-compatible provider maps unsupported roles."""

    def test_developer_role_mapped_to_system(self) -> None:
        messages = [
            {"role": "system", "content": "You are a helper."},
            {"role": "developer", "content": "Return JSON."},
            {"role": "user", "content": "Make a bracket."},
        ]
        normalized = OpenAICompatibleProvider._normalize_messages(messages)
        assert normalized[0]["role"] == "system"
        assert normalized[1]["role"] == "system"  # developer → system
        assert normalized[2]["role"] == "user"

    def test_unknown_roles_pass_through(self) -> None:
        messages = [
            {"role": "assistant", "content": "Here is the result."},
        ]
        normalized = OpenAICompatibleProvider._normalize_messages(messages)
        assert normalized[0]["role"] == "assistant"

    def test_empty_messages_produce_empty_list(self) -> None:
        normalized = OpenAICompatibleProvider._normalize_messages([])
        assert normalized == []


class TestSchemaGuardFeatureFlagNormalization:
    """Verify that string-valued feature flags are auto-normalized to objects."""

    def test_string_flag_normalized_to_object(self) -> None:
        result = validate_intent_translation(
            {
                "object_type": "wall_mounted_bracket",
                "units": "mm",
                "parameters": {"width": 120, "height": 80, "thickness": 6},
                "feature_flags": {
                    "mounting_holes": "requested_by_user",
                    "center_cutout": "omitted",
                },
                "assumptions": [],
                "unknowns": [],
                "warnings": [],
            },
            "Make a wall-mounted bracket 120mm wide 80mm tall.",
        )
        # The normalized prompt should be produced (schema guard passed)
        assert result.normalized_prompt
        # The original LLM output had strings, but schema guard normalized them
        assert result.parsed.intent.family == "wall_mounted_bracket"

    def test_object_flag_passes_unchanged(self) -> None:
        result = validate_intent_translation(
            {
                "object_type": "wall_mounted_bracket",
                "units": "mm",
                "parameters": {"width": 120},
                "feature_flags": {
                    "mounting_holes": {"state": "requested_by_user", "reason": "Prompt mentioned holes."},
                },
                "assumptions": [],
                "unknowns": [],
                "warnings": [],
            },
            "Make a wall-mounted bracket with holes.",
        )
        assert result.normalized_prompt

    def test_invalid_string_flag_rejected(self) -> None:
        with pytest.raises(LLMSchemaGuardError, match="must be an object"):
            validate_intent_translation(
                {
                    "object_type": "wall_mounted_bracket",
                    "units": "mm",
                    "parameters": {"width": 120},
                    "feature_flags": {
                        "mounting_holes": "maybe_yes",
                    },
                    "assumptions": [],
                    "unknowns": [],
                    "warnings": [],
                },
                "Make a bracket.",
            )
