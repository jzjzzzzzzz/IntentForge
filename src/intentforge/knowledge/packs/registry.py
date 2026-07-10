"""Deterministic registry for loaded engineering knowledge rule packs."""

from __future__ import annotations

from typing import Iterable

from intentforge.knowledge.packs.loader import load_default_bracket_rule_packs
from intentforge.knowledge.packs.schema import RulePack
from intentforge.knowledge.schema import DesignKnowledgeRule


class RulePackRegistry:
    """In-memory deterministic registry for rule packs and flattened rules."""

    def __init__(self, packs: Iterable[RulePack] | None = None) -> None:
        self._packs = list(packs or [])
        self._by_id: dict[str, RulePack] = {}
        self._rule_sources: dict[str, dict[str, str]] = {}
        seen_rule_ids: set[str] = set()
        for pack in self._packs:
            if pack.pack_id in self._by_id:
                raise ValueError(f"duplicate rule pack id: {pack.pack_id}")
            self._by_id[pack.pack_id] = pack
            for rule in pack.rules:
                if rule.id in seen_rule_ids:
                    raise ValueError(f"duplicate rule id across rule packs: {rule.id}")
                seen_rule_ids.add(rule.id)
                self._rule_sources[rule.id] = {
                    "pack_id": pack.pack_id,
                    "pack_version": pack.pack_version,
                    "category": pack.category,
                    "source": pack.source or f"rule-pack:{pack.pack_id}",
                }

    @classmethod
    def load_default(cls, *, include_deprecated: bool = False) -> "RulePackRegistry":
        return cls(load_default_bracket_rule_packs(include_deprecated=include_deprecated))

    @property
    def packs(self) -> list[RulePack]:
        return list(self._packs)

    def add_pack(self, pack: RulePack) -> None:
        if pack.pack_id in self._by_id:
            raise ValueError(f"duplicate rule pack id: {pack.pack_id}")
        existing_rule_ids = set(self._rule_sources)
        duplicate_rules = sorted(existing_rule_ids.intersection({rule.id for rule in pack.rules}))
        if duplicate_rules:
            raise ValueError(f"duplicate rule id across rule packs: {', '.join(duplicate_rules)}")
        self._packs.append(pack)
        self._by_id[pack.pack_id] = pack
        for rule in pack.rules:
            self._rule_sources[rule.id] = {
                "pack_id": pack.pack_id,
                "pack_version": pack.pack_version,
                "category": pack.category,
                "source": pack.source or f"rule-pack:{pack.pack_id}",
            }

    def get_pack(self, pack_id: str) -> RulePack:
        return self._by_id[pack_id]

    def all_packs(self) -> list[RulePack]:
        return list(self._packs)

    def get_active_packs(self) -> list[RulePack]:
        return [pack for pack in self._packs if pack.status == "active"]

    def get_by_category(self, category: str) -> list[RulePack]:
        return [pack for pack in self._packs if pack.category == category]

    def get_for_model_family(self, model_family: str) -> list[RulePack]:
        return [pack for pack in self._packs if model_family in pack.supported_model_families]

    def count_packs(self) -> int:
        return len(self._packs)

    def flatten_rules(self, *, active_only: bool = True) -> list[DesignKnowledgeRule]:
        rules: list[DesignKnowledgeRule] = []
        for pack in self._packs:
            if active_only and pack.status != "active":
                continue
            for rule in pack.rules:
                if active_only and rule.status != "active":
                    continue
                rules.append(rule)
        return rules

    def count_rules(self, *, active_only: bool = True) -> int:
        return len(self.flatten_rules(active_only=active_only))

    def rule_sources(self) -> dict[str, dict[str, str]]:
        return {rule_id: dict(source) for rule_id, source in self._rule_sources.items()}
