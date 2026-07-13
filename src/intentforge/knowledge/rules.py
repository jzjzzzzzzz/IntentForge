"""Rule loading and registry helpers for engineering knowledge rules."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import ValidationError

from intentforge.knowledge.packs.loader import load_rule_packs
from intentforge.knowledge.packs.registry import RulePackRegistry
from intentforge.knowledge.packs.validation import validate_rule_packs
from intentforge.knowledge.schema import DesignKnowledgeRule


DEFAULT_RULE_RESOURCE = "bracket_rules.yaml"
ALLOWED_REASONING_METADATA_FIELDS = {
    "implications",
    "affects",
    "tradeoffs",
    "priority_weight",
    "can_conflict_with",
    "depends_on",
    "duplicates",
    "mitigates",
    "mitigated_by",
    "mitigation",
    "limitations",
    "reinforces",
}
RULE_REFERENCE_FIELDS = {
    "can_conflict_with",
    "depends_on",
    "duplicates",
    "mitigates",
    "mitigated_by",
    "reinforces",
}


def _default_rule_path() -> Path:
    return Path(str(resources.files("intentforge.knowledge.data").joinpath(DEFAULT_RULE_RESOURCE)))


def _read_rule_yaml(path: str | Path | None = None) -> tuple[dict[str, Any], str, Path | None]:
    if path is None:
        text = resources.files("intentforge.knowledge.data").joinpath(DEFAULT_RULE_RESOURCE).read_text(encoding="utf-8")
        source = DEFAULT_RULE_RESOURCE
        base_path = None
    else:
        source_path = Path(path)
        text = source_path.read_text(encoding="utf-8")
        source = str(source_path)
        base_path = source_path.parent

    raw = yaml.safe_load(text) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{source} must contain a YAML mapping")
    return raw, source, base_path


def _manifest_pack_sources(raw: dict[str, Any], base_path: Path | None) -> list[str | Path]:
    packs = raw.get("packs")
    if not isinstance(packs, list):
        raise ValueError("rule pack manifest must contain a top-level 'packs' list")
    sources: list[str | Path] = []
    for index, entry in enumerate(packs):
        if isinstance(entry, str):
            resource = entry
        elif isinstance(entry, dict):
            resource = entry.get("resource")
        else:
            raise ValueError(f"rule pack manifest entry {index} must be a string or mapping")
        if not isinstance(resource, str) or not resource.strip():
            raise ValueError(f"rule pack manifest entry {index} is missing resource")
        if base_path is not None:
            candidate = base_path / resource
            sources.append(candidate if candidate.exists() else resource)
        else:
            sources.append(resource)
    return sources


def _load_rules_and_sources(path: str | Path | None = None) -> tuple[list[DesignKnowledgeRule], dict[str, dict[str, str]]]:
    raw, source, base_path = _read_rule_yaml(path)
    rules = raw.get("rules")
    if isinstance(rules, list):
        parsed_rules = [DesignKnowledgeRule.model_validate(rule) for rule in rules]
        return parsed_rules, {
            rule.id: {
                "pack_id": "legacy_bracket_rules",
                "pack_version": "1.0",
                "category": rule.category,
                "source": source,
            }
            for rule in parsed_rules
        }
    if raw.get("kind") == "rule_pack_manifest" or "packs" in raw:
        pack_registry = RulePackRegistry(load_rule_packs(_manifest_pack_sources(raw, base_path)))
        return pack_registry.flatten_rules(), pack_registry.rule_sources()
    raise ValueError(f"{source} must contain a top-level 'rules' list or rule pack manifest")


def load_rules(path: str | Path | None = None) -> list[DesignKnowledgeRule]:
    """Load deterministic engineering rules from YAML or rule-pack manifest."""

    return _load_rules_and_sources(path)[0]


def validate_rule_data(path: str | Path | None = None) -> dict[str, Any]:
    """Validate rule YAML integrity without raising on the first error."""

    errors: list[dict[str, Any]] = []
    raw, source, base_path = _read_rule_yaml(path)
    rules = raw.get("rules")
    if raw.get("kind") == "rule_pack_manifest" or "packs" in raw:
        try:
            packs = load_rule_packs(_manifest_pack_sources(raw, base_path), include_deprecated=True)
            result = validate_rule_packs(packs)
        except (ValueError, FileNotFoundError, ValidationError) as exc:
            return {
                "ok": False,
                "source": source,
                "rules_checked": 0,
                "errors": [{"rule_id": None, "message": str(exc)}],
            }
        return {
            "ok": result.passed,
            "source": source,
            "rules_checked": result.rules_checked,
            "errors": result.errors,
            "warnings": result.warnings,
            "pack_validation": result.model_dump(mode="json"),
        }
    if not isinstance(rules, list):
        return {
            "ok": False,
            "source": source,
            "rules_checked": 0,
            "errors": [{"rule_id": None, "message": "missing top-level rules list"}],
        }

    seen_ids: set[str] = set()
    for index, raw_rule in enumerate(rules):
        rule_id = raw_rule.get("id") if isinstance(raw_rule, dict) else None
        if not rule_id:
            errors.append({"rule_id": None, "index": index, "message": "missing rule id"})
        elif rule_id in seen_ids:
            errors.append({"rule_id": rule_id, "index": index, "message": "duplicate rule id"})
        else:
            seen_ids.add(rule_id)

        if not isinstance(raw_rule, dict):
            errors.append({"rule_id": rule_id, "index": index, "message": "rule must be a mapping"})
            continue

        for required_field in ("category", "severity", "confidence"):
            if required_field not in raw_rule:
                errors.append({"rule_id": rule_id, "index": index, "message": f"missing {required_field}"})
        try:
            DesignKnowledgeRule.model_validate(raw_rule)
        except ValidationError as exc:
            for error in exc.errors():
                location = ".".join(str(part) for part in error.get("loc", []))
                errors.append(
                    {
                        "rule_id": rule_id,
                        "index": index,
                        "field": location,
                        "message": error.get("msg", "invalid rule"),
                    }
                )

    return {
        "ok": not errors,
        "source": source,
        "rules_checked": len(rules),
        "errors": errors,
    }


def validate_reasoning_metadata(path: str | Path | None = None) -> dict[str, Any]:
    """Validate optional declarative reasoning metadata in the rule database."""

    try:
        rules = load_rules(path)
    except (ValueError, ValidationError) as exc:
        return {
            "ok": False,
            "rules_checked": 0,
            "metadata_errors": [{"rule_id": None, "message": str(exc)}],
            "interaction_links_validated": 0,
            "tradeoff_definitions_validated": 0,
        }

    rule_ids = {rule.id for rule in rules}
    metadata_errors: list[dict[str, Any]] = []
    interaction_links_validated = 0
    tradeoff_definitions_validated = 0

    for rule in rules:
        reasoning = rule.reasoning or {}
        unsupported = sorted(set(reasoning) - ALLOWED_REASONING_METADATA_FIELDS)
        for field_name in unsupported:
            metadata_errors.append(
                {
                    "rule_id": rule.id,
                    "field": f"reasoning.{field_name}",
                    "message": "unsupported reasoning metadata field",
                }
            )

        priority_weight = reasoning.get("priority_weight")
        if priority_weight is not None and not (
            isinstance(priority_weight, int | float) and 0.0 <= float(priority_weight) <= 1.0
        ):
            metadata_errors.append(
                {
                    "rule_id": rule.id,
                    "field": "reasoning.priority_weight",
                    "message": "priority_weight must be between 0 and 1",
                }
            )

        for field_name in RULE_REFERENCE_FIELDS:
            references = reasoning.get(field_name, [])
            if references is None:
                continue
            if not isinstance(references, list):
                metadata_errors.append(
                    {
                        "rule_id": rule.id,
                        "field": f"reasoning.{field_name}",
                        "message": "rule references must be a list",
                    }
                )
                continue
            seen_references: set[str] = set()
            for reference in references:
                if not isinstance(reference, str) or not reference:
                    metadata_errors.append(
                        {
                            "rule_id": rule.id,
                            "field": f"reasoning.{field_name}",
                            "message": "rule references must be non-empty strings",
                        }
                    )
                    continue
                if reference in seen_references:
                    metadata_errors.append(
                        {
                            "rule_id": rule.id,
                            "field": f"reasoning.{field_name}",
                            "message": f"duplicate rule reference: {reference}",
                        }
                    )
                seen_references.add(reference)
                if reference not in rule_ids:
                    metadata_errors.append(
                        {
                            "rule_id": rule.id,
                            "field": f"reasoning.{field_name}",
                            "message": f"unknown referenced rule id: {reference}",
                        }
                    )
                else:
                    interaction_links_validated += 1

        affects = reasoning.get("affects", [])
        if affects is not None and not (
            isinstance(affects, list) and all(isinstance(item, str) and item for item in affects)
        ):
            metadata_errors.append(
                {
                    "rule_id": rule.id,
                    "field": "reasoning.affects",
                    "message": "affected parameters must be a list of strings",
                }
            )

        mitigation = reasoning.get("mitigation")
        if mitigation is not None and not (isinstance(mitigation, str) and mitigation.strip()):
            metadata_errors.append(
                {
                    "rule_id": rule.id,
                    "field": "reasoning.mitigation",
                    "message": "mitigation must be a non-empty string",
                }
            )

        tradeoffs = reasoning.get("tradeoffs", []) or []
        if not isinstance(tradeoffs, list):
            metadata_errors.append(
                {
                    "rule_id": rule.id,
                    "field": "reasoning.tradeoffs",
                    "message": "tradeoffs must be a list",
                }
            )
            continue
        for index, tradeoff in enumerate(tradeoffs):
            if not isinstance(tradeoff, dict):
                metadata_errors.append(
                    {
                        "rule_id": rule.id,
                        "field": f"reasoning.tradeoffs[{index}]",
                        "message": "tradeoff must be a mapping",
                    }
                )
                continue
            for field_name in ("benefit", "cost"):
                if not isinstance(tradeoff.get(field_name), str) or not tradeoff[field_name].strip():
                    metadata_errors.append(
                        {
                            "rule_id": rule.id,
                            "field": f"reasoning.tradeoffs[{index}].{field_name}",
                            "message": f"tradeoff {field_name} must be non-empty",
                        }
                    )
            affected = tradeoff.get("affected_parameters", [])
            if not isinstance(affected, list) or not all(isinstance(item, str) and item for item in affected):
                metadata_errors.append(
                    {
                        "rule_id": rule.id,
                        "field": f"reasoning.tradeoffs[{index}].affected_parameters",
                        "message": "affected_parameters must be a list of strings",
                    }
                )
            else:
                tradeoff_definitions_validated += 1

    return {
        "ok": not metadata_errors,
        "rules_checked": len(rules),
        "metadata_errors": metadata_errors,
        "interaction_links_validated": interaction_links_validated,
        "tradeoff_definitions_validated": tradeoff_definitions_validated,
    }


class RuleRegistry:
    """In-memory deterministic registry for design knowledge rules."""

    def __init__(
        self,
        rules: Iterable[DesignKnowledgeRule] | None = None,
        *,
        rule_sources: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._rules = list(rules or [])
        self._by_id = {rule.id: rule for rule in self._rules}
        if len(self._by_id) != len(self._rules):
            raise ValueError("duplicate knowledge rule id")
        self._rule_sources = dict(rule_sources or {})

    @classmethod
    def load(cls, path: str | Path | None = None) -> "RuleRegistry":
        rules, rule_sources = _load_rules_and_sources(path)
        return cls(rules, rule_sources=rule_sources)

    @property
    def rules(self) -> list[DesignKnowledgeRule]:
        return list(self._rules)

    def get_by_category(self, category: str) -> list[DesignKnowledgeRule]:
        return [rule for rule in self._rules if rule.category == category]

    def get_active_rules(self) -> list[DesignKnowledgeRule]:
        return [rule for rule in self._rules if rule.status == "active"]

    def count(self) -> int:
        return len(self._rules)

    def for_family(self, family: str) -> list[DesignKnowledgeRule]:
        direct = [rule for rule in self._rules if family in rule.applies_to]
        if direct:
            return direct
        try:
            from intentforge.topology.registry import get_topology_registry

            bound_ids = get_topology_registry().get(family).capability_evidence_binding.rule_ids
        except (ImportError, ValueError):
            return []
        return [self._by_id[rule_id] for rule_id in bound_ids if rule_id in self._by_id]

    def get(self, rule_id: str) -> DesignKnowledgeRule:
        return self._by_id[rule_id]

    def rule_sources(self) -> dict[str, dict[str, str]]:
        return {rule_id: dict(source) for rule_id, source in self._rule_sources.items()}

    def __len__(self) -> int:
        return len(self._rules)
