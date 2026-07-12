"""Deterministic semantic pruning engine for privacy-preserving audit export."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from intentforge.redaction.config import (
    REDACTION_SCHEMA_VERSION,
    RedactionConfig,
    RedactionRule,
    default_redaction_config,
    load_redaction_config,
)


@dataclass(frozen=True)
class RedactionResult:
    """Result of a single field redaction operation."""
    path: str
    field_name: str
    original_value: Any
    redacted_value: str
    rule_name: str
    token_type: str


@dataclass(frozen=True)
class PruningResult:
    """Complete result of the semantic pruning operation."""
    passed: bool
    original_document: Any
    redacted_document: Any
    redactions: tuple[RedactionResult, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "redaction_count": len(self.redactions),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": dict(sorted(self.metrics.items())),
            "redaction_schema_version": REDACTION_SCHEMA_VERSION,
        }


def _build_path(parent: str, key: str | int, index: int | None = None) -> str:
    """Build a deterministic JSON path for diagnostics."""
    if isinstance(key, int):
        return f"{parent}[{key}]"
    if parent:
        return f"{parent}.{key}"
    return key


def _deep_copy(value: Any) -> Any:
    """Create a deep copy that preserves structure."""
    if isinstance(value, dict):
        return {k: _deep_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


class SemanticPruner:
    """Deterministic semantic pruning engine for JSON-like documents."""

    def __init__(self, config: RedactionConfig):
        self.config = config
        self._redactions: list[RedactionResult] = []
        self._errors: list[str] = []
        self._warnings: list[str] = []

    def prune(self, document: Any) -> PruningResult:
        """Apply semantic pruning to the document."""
        self._redactions = []
        self._errors = []
        self._warnings = []
        original = _deep_copy(document)
        redacted = self._prune_value(document, "$")
        return PruningResult(
            passed=len(self._errors) == 0,
            original_document=original,
            redacted_document=redacted,
            redactions=tuple(self._redactions),
            errors=tuple(self._errors),
            warnings=tuple(self._warnings),
            metrics=self._compute_metrics(),
        )

    def _prune_value(self, value: Any, path: str, parent_name: str | None = None) -> Any:
        """Recursively prune a value at the given path."""
        if isinstance(value, dict):
            return self._prune_dict(value, path)
        if isinstance(value, list):
            return self._prune_list(value, path)
        return value

    def _prune_dict(self, data: dict[str, Any], path: str, parent_name: str | None = None) -> dict[str, Any]:
        """Prune a dictionary, applying redactions as needed."""
        result: dict[str, Any] = {}
        list_field = "value" if "name" in data else None
        for key in sorted(data.keys()):
            child_path = _build_path(path, key)
            child_value = data[key]
            rule = self.config.should_redact(child_path, key, child_value)
            if rule is None and key == list_field:
                target_name = data.get("name") if isinstance(data.get("name"), str) else parent_name
                if target_name is not None:
                    synthetic_name_path = f"{path}[{target_name}]"
                    rule = self.config.should_redact(synthetic_name_path, target_name, child_value)
            if rule is not None:
                redacted = rule.redact_value(child_value)
                self._redactions.append(RedactionResult(
                    path=child_path,
                    field_name=key,
                    original_value=_deep_copy(child_value),
                    redacted_value=redacted,
                    rule_name=rule.name,
                    token_type=rule.token_type,
                ))
                if rule.preserve_structure:
                    result[key] = redacted
                else:
                    continue
            else:
                next_parent_name = data.get("name") if isinstance(data.get("name"), str) else None
                result[key] = self._prune_value(child_value, child_path, parent_name=next_parent_name)
        return result

    def _prune_list(self, items: list[Any], path: str) -> list[Any]:
        """Prune a list, applying redactions as needed."""
        result: list[Any] = []
        for index, item in enumerate(items):
            child_path = _build_path(path, f"[{index}]")
            if isinstance(item, dict):
                result.append(self._prune_dict(item, child_path))
            elif isinstance(item, list):
                result.append(self._prune_list(item, child_path))
            else:
                result.append(item)
        return result

    def _compute_metrics(self) -> dict[str, Any]:
        """Compute redaction metrics."""
        by_rule: dict[str, int] = {}
        by_token_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        for r in self._redactions:
            by_rule[r.rule_name] = by_rule.get(r.rule_name, 0) + 1
            by_token_type[r.token_type] = by_token_type.get(r.token_type, 0) + 1
        return {
            "total_redactions": len(self._redactions),
            "redactions_by_rule": dict(sorted(by_rule.items())),
            "redactions_by_token_type": dict(sorted(by_token_type.items())),
        }


def prune_document(document: Any, config: RedactionConfig | None = None) -> PruningResult:
    """Apply semantic pruning to a document using the provided or default config."""
    cfg = config or default_redaction_config()
    pruner = SemanticPruner(cfg)
    return pruner.prune(document)


def prune_json_file(
    input_path: str | Path,
    output_path: str | Path,
    config: RedactionConfig | None = None,
) -> PruningResult:
    """Prune a JSON file and write the redacted result."""
    cfg = config or default_redaction_config()
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    result = prune_document(data, cfg)
    redacted_json = json.dumps(
        result.redacted_document,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
        separators=(",", ": "),
    ) + "\n"
    Path(output_path).write_text(redacted_json, encoding="utf-8")
    return result
