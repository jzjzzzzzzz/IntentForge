"""Rule loading and registry helpers for engineering knowledge rules."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Iterable

import yaml

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

    def for_family(self, family: str) -> list[DesignKnowledgeRule]:
        return [rule for rule in self._rules if family in rule.applies_to]

    def get(self, rule_id: str) -> DesignKnowledgeRule:
        return self._by_id[rule_id]

    def __len__(self) -> int:
        return len(self._rules)
