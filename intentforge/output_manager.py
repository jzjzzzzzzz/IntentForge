"""Parsed-run output management and traceability helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from intentforge.features import OPTIONAL_FEATURES, feature_flags_for_parameter_table, is_feature_active

MAX_PROMPT_SLUG_LENGTH = 64


@dataclass(frozen=True)
class ParsedRunContext:
    """Reserved output directory for one parse or parse-build command."""

    run_id: str
    run_dir: Path
    created_at: datetime


def _coerce_datetime(created_at: datetime | None = None) -> datetime:
    if created_at is None:
        return datetime.now().astimezone()
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at


def prompt_slug(prompt: str, max_length: int = MAX_PROMPT_SLUG_LENGTH) -> str:
    """Return a short filesystem-safe slug derived from the prompt."""

    compact_units = re.sub(
        r"\b(\d+(?:\.\d+)?)\s*(mm|millimeters?|millimetres?)\b",
        lambda match: f"{match.group(1).replace('.', 'p')}mm",
        prompt.lower(),
    )
    tokens = re.findall(r"[a-z0-9]+", compact_units)
    stop_words = {
        "a",
        "an",
        "and",
        "create",
        "design",
        "for",
        "i",
        "make",
        "need",
        "the",
        "to",
        "with",
    }
    significant_tokens = [token for token in tokens if token not in stop_words]
    slug = "_".join(significant_tokens) or "prompt"
    slug = slug[:max_length].strip("_")
    return slug or "prompt"


def make_run_id(prompt: str, created_at: datetime | None = None) -> str:
    """Create the base run ID before collision handling."""

    timestamp = _coerce_datetime(created_at).strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{prompt_slug(prompt)}"


def create_parsed_run_context(
    prompt: str,
    output_dir: str | Path,
    created_at: datetime | None = None,
) -> ParsedRunContext:
    """Reserve a unique parsed_runs/<run_id> directory."""

    return create_run_context(prompt, output_dir, "parsed_runs", created_at)


def create_run_context(
    prompt: str,
    output_dir: str | Path,
    runs_subdir: str,
    created_at: datetime | None = None,
) -> ParsedRunContext:
    """Reserve a unique run directory below an output subdirectory."""

    output_path = Path(output_dir)
    runs_dir = output_path / runs_subdir
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_created_at = _coerce_datetime(created_at)
    base_run_id = make_run_id(prompt, run_created_at)
    run_id = base_run_id
    suffix = 2
    while True:
        run_dir = runs_dir / run_id
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            return ParsedRunContext(run_id=run_id, run_dir=run_dir, created_at=run_created_at)
        except FileExistsError:
            run_id = f"{base_run_id}_{suffix}"
            suffix += 1


def feature_state_names(parameter_table) -> tuple[list[str], list[str]]:
    """Return active and omitted feature names for run metadata."""

    flags = feature_flags_for_parameter_table(parameter_table)
    active = [feature for feature in OPTIONAL_FEATURES if is_feature_active(flags, feature)]
    omitted = [feature for feature in OPTIONAL_FEATURES if feature not in active]
    return active, omitted


def json_safe_paths(paths: dict[str, Any]) -> dict[str, Any]:
    """Convert nested path dictionaries into JSON-safe strings."""

    safe: dict[str, Any] = {}
    for key, value in paths.items():
        if isinstance(value, Path):
            safe[key] = str(value)
        elif isinstance(value, dict):
            safe[key] = json_safe_paths(value)
        else:
            safe[key] = value
    return safe


def build_run_metadata(
    *,
    run_context: ParsedRunContext,
    command_type: str,
    prompt: str,
    object_type: str,
    active_features: list[str],
    omitted_features: list[str],
    warnings: list[str],
    output_paths: dict[str, Any],
    validation_valid: bool | None = None,
) -> dict[str, Any]:
    """Build trace metadata for a parse or parse-build run."""

    metadata: dict[str, Any] = {
        "run_id": run_context.run_id,
        "command_type": command_type,
        "original_prompt": prompt,
        "created_at": run_context.created_at.isoformat(),
        "object_type": object_type,
        "active_features": active_features,
        "omitted_features": omitted_features,
        "warnings": warnings,
        "output_paths": json_safe_paths(output_paths),
    }
    if validation_valid is not None:
        metadata["validation_valid"] = validation_valid
    return metadata


def write_run_metadata(metadata: dict[str, Any], path: str | Path) -> Path:
    """Write run_metadata.json."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
