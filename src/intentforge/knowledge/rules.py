"""Rule loading and registry helpers for engineering knowledge rules."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import ValidationError

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


def load_rules(path: str | Path | None = None) -> list[DesignKnowledgeRule]:
    """Load deterministic engineering rules from YAML."""

    if path is None:
        text = resources.files("intentforge.knowledge.data").joinpath(DEFAULT_RULE_RESOURCE).read_text(encoding="utf-8")
        source = DEFAULT_RULE_RESOURCE
    else:
        source_path = Path(path)
        text = source_path.read_text(encoding="utf-8")
        source = str(source_path)

    raw = yaml.safe_load(text) or {}
    rules = raw.get("rules")
    if not isinstance(rules, list):
        raise ValueError(f"{source} must contain a top-level 'rules' list")
    return [DesignKnowledgeRule.model_validate(rule) for rule in rules]


def validate_rule_data(path: str | Path | None = None) -> dict[str, Any]:
    """Validate rule YAML integrity without raising on the first error."""

    if path is None:
        text = resources.files("intentforge.knowledge.data").joinpath(DEFAULT_RULE_RESOURCE).read_text(encoding="utf-8")
        source = DEFAULT_RULE_RESOURCE
    else:
        source_path = Path(path)
        text = source_path.read_text(encoding="utf-8")
        source = str(source_path)

    errors: list[dict[str, Any]] = []
    raw = yaml.safe_load(text) or {}
    rules = raw.get("rules")
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

    def __init__(self, rules: Iterable[DesignKnowledgeRule] | None = None) -> None:
        self._rules = list(rules or [])
        self._by_id = {rule.id: rule for rule in self._rules}
        if len(self._by_id) != len(self._rules):
            raise ValueError("duplicate knowledge rule id")

    @classmethod
    def load(cls, path: str | Path | None = None) -> "RuleRegistry":
        return cls(load_rules(path))

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
        return [rule for rule in self._rules if family in rule.applies_to]

    def get(self, rule_id: str) -> DesignKnowledgeRule:
        return self._by_id[rule_id]

    def __len__(self) -> int:
        return len(self._rules)
