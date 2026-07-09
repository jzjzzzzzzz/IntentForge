"""High-level optional LLM translation workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intentforge.contracts import apply_response_contract, ensure_request_id, error_response
from intentforge.llm.prompts import edit_translation_messages, intent_translation_messages
from intentforge.llm.provider import LLMProvider
from intentforge.llm.schema_guard import (
    LLMSchemaGuardError,
    validate_edit_translation,
    validate_intent_translation,
)
from intentforge.workflows import edit_parse_apply_workflow, parse_build_workflow


def _provider_unavailable(operation: str, request_id: str) -> dict[str, Any]:
    return error_response(
        operation=operation,
        request_id=request_id,
        error_type="LLMProviderUnavailableError",
        message=(
            "No LLM provider is configured. Set INTENTFORGE_LLM_PROVIDER or use "
            "the mock provider for deterministic local testing."
        ),
        recoverable=True,
        suggested_action="Configure an optional LLM provider or run with --mock-provider.",
    )


def translate_prompt_to_intent(
    prompt: str,
    provider: LLMProvider | None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Translate natural language into guarded IntentForge intent JSON."""

    request_id = ensure_request_id(request_id)
    if provider is None:
        return _provider_unavailable("llm_parse", request_id)
    try:
        llm_output = provider.complete_json(intent_translation_messages(prompt), "intent_translation")
        guarded = validate_intent_translation(llm_output, prompt)
    except LLMSchemaGuardError as exc:
        return error_response(
            operation="llm_parse",
            request_id=request_id,
            error_type="UnsupportedObjectError",
            message=str(exc),
            recoverable=True,
            suggested_action="Revise the prompt to use a supported model family and supported features.",
        )
    except Exception as exc:
        return error_response(
            operation="llm_parse",
            request_id=request_id,
            error_type=type(exc).__name__,
            message=str(exc),
            recoverable=True,
        )

    parsed = guarded.parsed
    result: dict[str, Any] = {
        "ok": True,
        "object_type": parsed.intent.family,
        "intent": parsed.intent.model_dump(mode="json"),
        "parameters": parsed.parameter_table.model_dump(mode="json"),
        "constraints": parsed.constraint_graph.model_dump(mode="json"),
        "feature_plan": parsed.feature_plan.model_dump(mode="json"),
        "warnings": [*guarded.warnings, *parsed.warnings],
        "assumptions": parsed.intent.assumptions,
        "unknowns": parsed.intent.unknowns,
        "active_features": [
            name
            for name, flag in parsed.parameter_table.metadata.get("feature_flags", {}).items()
            if flag.get("state") in {"requested_by_user", "defaulted_by_system"}
        ],
        "omitted_features": [
            name
            for name, flag in parsed.parameter_table.metadata.get("feature_flags", {}).items()
            if flag.get("state") == "omitted"
        ],
        "llm_output": guarded.llm_output,
        "normalized_prompt": guarded.normalized_prompt,
    }
    return apply_response_contract(
        result,
        operation="llm_parse",
        request_id=request_id,
        object_type=parsed.intent.family,
        metadata={
            "llm": {
                "schema_name": "intent_translation",
                "normalized_prompt": guarded.normalized_prompt,
                "llm_output": guarded.llm_output,
            }
        },
    )


def translate_prompt_to_build(
    prompt: str,
    provider: LLMProvider | None,
    output_root: str | Path | None = None,
    *,
    request_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Translate with LLM guardrails, then build through deterministic workflows."""

    request_id = ensure_request_id(request_id)
    translation = translate_prompt_to_intent(prompt, provider, request_id=request_id)
    if not translation.get("ok"):
        translation["operation"] = "llm_parse_build"
        return translation
    normalized_prompt = translation["normalized_prompt"]
    build_result = parse_build_workflow(
        normalized_prompt,
        output_root,
        request_id=request_id,
        dry_run=dry_run,
    )
    build_result["operation"] = "llm_parse_build"
    build_result["llm_translation"] = translation
    build_result["metadata"]["llm"] = {
        "schema_name": "intent_translation",
        "original_prompt": prompt,
        "normalized_prompt": normalized_prompt,
        "llm_output": translation["llm_output"],
    }
    return build_result


def translate_edit_to_request(
    edit_text: str,
    object_type: str,
    provider: LLMProvider | None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Translate natural-language edit text into guarded structured edit JSON."""

    request_id = ensure_request_id(request_id)
    if provider is None:
        return _provider_unavailable("llm_edit_parse", request_id)
    try:
        llm_output = provider.complete_json(edit_translation_messages(edit_text, object_type), "edit_translation")
        guarded = validate_edit_translation(llm_output, edit_text, object_type)
    except LLMSchemaGuardError as exc:
        return error_response(
            operation="llm_edit_parse",
            request_id=request_id,
            object_type=object_type if object_type in {"wall_mounted_bracket", "l_bracket"} else None,
            error_type="EditRejectedError",
            message=str(exc),
            recoverable=True,
            suggested_action="Revise the edit to use measurable parameters and supported features.",
        )
    except Exception as exc:
        return error_response(
            operation="llm_edit_parse",
            request_id=request_id,
            object_type=object_type if object_type in {"wall_mounted_bracket", "l_bracket"} else None,
            error_type=type(exc).__name__,
            message=str(exc),
            recoverable=True,
        )
    result = {
        "ok": True,
        "object_type": object_type,
        "edit_request": guarded.edit_request,
        "warnings": guarded.warnings,
        "assumptions": guarded.edit_request.get("assumptions", []),
        "llm_output": guarded.llm_output,
        "normalized_edit_text": guarded.normalized_edit_text,
    }
    return apply_response_contract(
        result,
        operation="llm_edit_parse",
        request_id=request_id,
        object_type=object_type,
        metadata={
            "llm": {
                "schema_name": "edit_translation",
                "normalized_edit_text": guarded.normalized_edit_text,
                "llm_output": guarded.llm_output,
            }
        },
    )


def _target_for_object_type(object_type: str) -> str:
    if object_type in {"wall_mounted_bracket", "bracket"}:
        return "bracket"
    if object_type == "l_bracket":
        return "l_bracket"
    raise ValueError(f"unsupported object_type: {object_type}")


def translate_edit_apply(
    edit_text: str,
    object_type: str,
    provider: LLMProvider | None,
    output_root: str | Path | None = None,
    *,
    request_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Translate an edit with guardrails, then apply through deterministic workflows."""

    request_id = ensure_request_id(request_id)
    translation = translate_edit_to_request(edit_text, object_type, provider, request_id=request_id)
    if not translation.get("ok"):
        translation["operation"] = "llm_edit_apply"
        return translation
    target = _target_for_object_type(object_type)
    result = edit_parse_apply_workflow(
        target,
        translation["normalized_edit_text"],
        output_root,
        request_id=request_id,
        dry_run=dry_run,
    )
    result["operation"] = "llm_edit_apply"
    result["llm_translation"] = translation
    result["metadata"]["llm"] = {
        "schema_name": "edit_translation",
        "original_edit_text": edit_text,
        "normalized_edit_text": translation["normalized_edit_text"],
        "llm_output": translation["llm_output"],
    }
    return result
