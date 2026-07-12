"""Declarative redaction configuration schema for privacy-preserving audit export."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

import yaml


REDACTION_SCHEMA_VERSION = "1.0"
REdactionTokenType = Literal["redacted_geometry", "redacted_position", "redacted_material", "redacted_numeric", "redacted_hash"]


class RedactionFieldSelector:
    """Selects fields to redact from JSON-like structures."""

    def __init__(
        self,
        *,
        path_pattern: str | None = None,
        field_name_pattern: str | None = None,
        value_type: str | None = None,
        value_range: tuple[float, float] | None = None,
        semantic_tag: str | None = None,
    ):
        self.path_pattern = re.compile(path_pattern) if path_pattern else None
        self.field_name_pattern = re.compile(field_name_pattern) if field_name_pattern else None
        self.value_type = value_type
        self.value_range = value_range
        self.semantic_tag = semantic_tag

    def matches(self, path: str, field_name: str, value: Any) -> bool:
        if self.field_name_pattern and not self.field_name_pattern.search(field_name):
            return False
        if self.path_pattern and not self.path_pattern.search(path):
            return False
        if self.value_type:
            if self.value_type == "numeric" and not isinstance(value, (int, float)):
                return False
            if self.value_type == "string" and not isinstance(value, str):
                return False
        if self.value_range is not None and isinstance(value, (int, float)):
            if not (self.value_range[0] <= value <= self.value_range[1]):
                return False
        return True


class RedactionRule:
    """Single redaction rule with field selector and replacement strategy."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        severity: Literal["high", "medium", "low"],
        selectors: list[dict[str, Any]],
        token_type: RedactionTokenType,
        salt: str | None = None,
        preserve_structure: bool = True,
    ):
        self.name = name
        self.description = description
        self.severity = severity
        self.salt = salt or "intentforge-default-salt"
        self.token_type = token_type
        self.preserve_structure = preserve_structure
        self._selectors = [RedactionFieldSelector(**s) for s in selectors]

    def matches(self, path: str, field_name: str, value: Any) -> bool:
        return any(s.matches(path, field_name, value) for s in self._selectors)

    def redact_value(self, value: Any) -> str:
        if self.token_type == "redacted_hash":
            canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
            salted = f"{self.salt}:{canonical}".encode("utf-8")
            return f"[REDACTED_HASH_{hashlib.sha256(salted).hexdigest()[:16]}]"
        if self.token_type == "redacted_geometry":
            return "[REDACTED_GEOMETRY_VALUE]"
        if self.token_type == "redacted_position":
            return "[REDACTED_POSITION_VALUE]"
        if self.token_type == "redacted_material":
            return "[REDACTED_MATERIAL_VALUE]"
        return "[REDACTED_NUMERIC_VALUE]"


class RedactionConfig:
    """Complete redaction configuration for audit package export."""

    def __init__(
        self,
        *,
        version: str = REDACTION_SCHEMA_VERSION,
        description: str = "",
        rules: list[RedactionRule],
        preserve_keys: set[str] | None = None,
        protected_paths: list[str] | None = None,
    ):
        self.version = version
        self.description = description
        self.rules = rules
        self.preserve_keys = preserve_keys or {
            "claim_id", "argument_id", "validation_id", "content_id", "assurance_case_id",
            "decision_id", "provenance_id", "snapshot_id", "node_id", "finding_id",
            "condition_id", "check_id", "policy_id", "capability_id", "evidence_id",
            "rule_id", "limitation_id", "package_id", "content_address",
            "predecessor_hash_pointer", "schema_version", "operation", "cad_family",
            "claim_type", "family", "status", "severity", "check_type",
            "validation_type", "evidence_role", "rule_pack", "subject_type",
            "decision_status", "assurance_profile", "profile", "tool_version",
        }
        self.protected_paths = protected_paths or [
            r"\.claim_id$",
            r"\.argument_id$",
            r"\.validation_id$",
            r"\.content_id$",
            r"\.assurance_case_id$",
            r"\.decision_id$",
            r"\.provenance_id$",
            r"\.snapshot_id$",
            r"\.node_id$",
            r"\.finding_id$",
            r"\.condition_id$",
            r"\.check_id$",
            r"\.policy_id$",
            r"\.capability_id$",
            r"\.evidence_id$",
            r"\.rule_id$",
            r"\.limitation_id$",
            r"\.package_id$",
            r"\.content_address$",
            r"\.predecessor_hash_pointer$",
            r"\.schema_version$",
            r"\.operation$",
            r"\.cad_family$",
            r"\.claim_type$",
            r"\.family$",
            r"\.status$",
            r"\.severity$",
            r"\.check_type$",
            r"\.validation_type$",
            r"\.evidence_role$",
            r"\.rule_pack$",
            r"\.subject_type$",
            r"\.decision_status$",
            r"\.assurance_profile$",
            r"\.profile$",
            r"\.tool_version$",
            r"^observations\[",
            r"^claims\[",
            r"^arguments\[",
            r"^validations\[",
            r"^checks\[",
            r"^findings\[",
            r"^conditions\[",
            r"^policies\[",
            r"^capabilities\[",
            r"^evidence\[",
            r"^rules\[",
            r"^limitations\[",
            r"^snapshots\[",
            r"^nodes\[",
            r"^artifact_records\[",
            r"^policy_catalog",
            r"^check_registry",
            r"^decision_strategy",
            r"^boundary_conditions",
        ]

    def should_protect(self, path: str) -> bool:
        for pattern in self.protected_paths:
            if re.search(pattern, path):
                return True
        return False

    def should_redact(self, path: str, field_name: str, value: Any) -> RedactionRule | None:
        if self.should_protect(path):
            return None
        for rule in self.rules:
            if rule.matches(path, field_name, value):
                return rule
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.version,
            "description": self.description,
            "preserve_keys": sorted(self.preserve_keys),
            "protected_paths": self.protected_paths,
            "rules": [
                {
                    "name": r.name,
                    "description": r.description,
                    "severity": r.severity,
                    "selectors": [
                        {k: v for k, v in sel.__dict__.items() if v is not None}
                        for sel in r._selectors
                    ],
                    "token_type": r.token_type,
                    "salt": r.salt,
                    "preserve_structure": r.preserve_structure,
                }
                for r in self.rules
            ],
        }


def load_redaction_config(path: str | Path) -> RedactionConfig:
    """Load redaction configuration from YAML or JSON file."""
    p = Path(path)
    if p.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    elif p.suffix == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
    else:
        data = json.loads(p.read_text(encoding="utf-8"))

    rules = [
        RedactionRule(
            name=r["name"],
            description=r["description"],
            severity=r["severity"],
            selectors=r["selectors"],
            token_type=r["token_type"],
            salt=r.get("salt"),
            preserve_structure=r.get("preserve_structure", True),
        )
        for r in data.get("rules", [])
    ]

    return RedactionConfig(
        version=data.get("schema_version", REDACTION_SCHEMA_VERSION),
        description=data.get("description", ""),
        rules=rules,
        preserve_keys=set(data.get("preserve_keys", [])),
        protected_paths=data.get("protected_paths"),
    )


def default_redaction_config() -> RedactionConfig:
    """Return the standard redaction configuration for privacy-preserving export."""
    return RedactionConfig(
        description="Default redaction configuration for IntentForge privacy-preserving audit export",
        rules=[
            RedactionRule(
                name="geometry_dimensions",
                description="Redact geometric dimension values (width, height, depth, thickness, etc.)",
                severity="high",
                selectors=[
                    {"field_name_pattern": r"^(width|height|depth|thickness|length|radius|diameter|size)$", "value_type": "numeric"},
                ],
                token_type="redacted_geometry",
                salt="intentforge-geometry-salt-v1",
            ),
            RedactionRule(
                name="position_values",
                description="Redact positional values (hole positions, offsets, spacing)",
                severity="high",
                selectors=[
                    {"field_name_pattern": r"^(x|y|z|x_pos|y_pos|z_pos|offset|spacing)$", "value_type": "numeric"},
                    {"field_name_pattern": r"position", "value_type": "numeric"},
                    {"field_name_pattern": r"offset", "value_type": "numeric"},
                    {"field_name_pattern": r"^(x|y|z)_(center|middle|min|max)$", "value_type": "numeric"},
                    {"path_pattern": r"\.(x_pos|y_pos|z_pos|x|y|z|offset|spacing)$", "value_type": "numeric"},
                ],
                token_type="redacted_position",
                salt="intentforge-position-salt-v1",
            ),
            RedactionRule(
                name="material_properties",
                description="Redact material and finish specifications",
                severity="medium",
                selectors=[
                    {"field_name_pattern": r"^(material|finish|coating|surface|treatment|alloy|grade)$"},
                    {"path_pattern": r"parameters\[", "field_name_pattern": r"material"},
                ],
                token_type="redacted_material",
                salt="intentforge-material-salt-v1",
            ),
            RedactionRule(
                name="numeric_parameters",
                description="Redact generic numeric parameter values",
                severity="low",
                selectors=[
                    {"path_pattern": r"parameters\[", "value_type": "numeric"},
                    {"path_pattern": r"constraints\[", "value_type": "numeric"},
                ],
                token_type="redacted_numeric",
                salt="intentforge-numeric-salt-v1",
            ),
        ],
    )
