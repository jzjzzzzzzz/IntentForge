"""MCP-facing tool functions for IntentForge.

These functions intentionally wrap shared IntentForge workflows instead of
implementing parser, generator, validator, or editor logic here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from intentforge.workflows import (
    build_example_workflow,
    edit_parse_apply_workflow,
    edit_parse_workflow,
    get_run_metadata_workflow,
    list_recent_runs_workflow,
    parse_build_workflow,
    parse_prompt_workflow,
    validate_example_workflow,
)

ToolCallable = Callable[..., dict[str, Any]]


def _structured_error(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "error_type": type(exc).__name__,
        "message": str(exc),
    }


def _call_workflow(workflow: ToolCallable, *args: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return workflow(*args, **kwargs)
    except Exception as exc:  # MCP tools must return structured errors.
        return _structured_error(exc)


def parse_cad_prompt(prompt: str) -> dict[str, Any]:
    """Parse a deterministic bracket CAD prompt for a supported model family."""

    return _call_workflow(parse_prompt_workflow, prompt)


def parse_build_cad_prompt(prompt: str, output_root: str | None = None) -> dict[str, Any]:
    """Parse, build, export, and validate a supported bracket prompt."""

    return _call_workflow(parse_build_workflow, prompt, output_root)


def parse_edit_prompt(edit_text: str) -> dict[str, Any]:
    """Parse a deterministic natural-language edit request."""

    return _call_workflow(edit_parse_workflow, edit_text)


def parse_apply_edit_prompt(
    target: str,
    edit_text: str,
    output_root: str | None = None,
) -> dict[str, Any]:
    """Parse and apply an edit to a bundled bracket or L-bracket example."""

    return _call_workflow(edit_parse_apply_workflow, target, edit_text, output_root)


def build_example_bracket(variant: str = "bracket", output_root: str | None = None) -> dict[str, Any]:
    """Build and export a bundled supported bracket example."""

    return _call_workflow(build_example_workflow, variant, output_root)


def validate_example_bracket(variant: str = "bracket", output_root: str | None = None) -> dict[str, Any]:
    """Validate a bundled supported bracket example."""

    return _call_workflow(validate_example_workflow, variant, output_root)


def list_recent_runs(
    kind: str = "parsed_runs",
    limit: int = 5,
    output_root: str | None = None,
) -> dict[str, Any]:
    """List recent parsed or edit-parse output runs."""

    return _call_workflow(list_recent_runs_workflow, kind, limit, output_root)


def get_run_metadata(
    kind: str,
    run_id: str,
    output_root: str | None = None,
) -> dict[str, Any]:
    """Return run_metadata.json for a parsed or edit-parse output run."""

    return _call_workflow(get_run_metadata_workflow, kind, run_id, output_root)


TOOLS: dict[str, ToolCallable] = {
    "parse_cad_prompt": parse_cad_prompt,
    "parse_build_cad_prompt": parse_build_cad_prompt,
    "parse_edit_prompt": parse_edit_prompt,
    "parse_apply_edit_prompt": parse_apply_edit_prompt,
    "build_example_bracket": build_example_bracket,
    "validate_example_bracket": validate_example_bracket,
    "list_recent_runs": list_recent_runs,
    "get_run_metadata": get_run_metadata,
}


def list_tools() -> list[dict[str, str]]:
    """Return MCP tool names and descriptions."""

    return [
        {"name": name, "description": (func.__doc__ or "").strip()}
        for name, func in sorted(TOOLS.items())
    ]
