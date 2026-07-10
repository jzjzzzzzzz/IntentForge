"""Rule loading and registry helpers for engineering knowledge rules."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import ValidationError

from intentforge.knowledge.schema import DesignKnowledgeRule


DEFAULT_RULE_RESOURCE = "bracket_rules.yaml"


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
