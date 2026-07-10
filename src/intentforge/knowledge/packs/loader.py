"""Load engineering knowledge rule packs from package data or explicit paths."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Iterable

import yaml

from intentforge.knowledge.packs.schema import RulePack


PACK_DATA_PACKAGE = "intentforge.knowledge.packs.data"
DEFAULT_BRACKET_PACK_RESOURCES = (
    "mechanical.yaml",
    "manufacturing.yaml",
    "assembly.yaml",
    "structural.yaml",
)


def _logical_resource_name(name: str) -> str:
    return f"{PACK_DATA_PACKAGE}/{name}"


def _read_pack_source(source: str | Path) -> tuple[str, str]:
    source_path = Path(source)
    if source_path.exists():
        return source_path.read_text(encoding="utf-8"), str(source_path)

    resource_name = str(source).replace("\\", "/").split("/")[-1]
    if resource_name not in DEFAULT_BRACKET_PACK_RESOURCES:
        raise FileNotFoundError(f"unknown packaged rule pack resource: {source}")
    resource = resources.files(PACK_DATA_PACKAGE).joinpath(resource_name)
    return resource.read_text(encoding="utf-8"), _logical_resource_name(resource_name)


def load_rule_pack(source: str | Path) -> RulePack:
    """Load one rule pack from a package resource name or filesystem path."""

    text, logical_source = _read_pack_source(source)
    raw = yaml.safe_load(text) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{logical_source} must contain a rule pack mapping")
    raw.setdefault("source", logical_source)
    return RulePack.model_validate(raw)


def load_rule_packs(
    sources: Iterable[str | Path] | None = None,
    *,
    include_deprecated: bool = False,
) -> list[RulePack]:
    """Load multiple rule packs in deterministic order."""

    selected_sources = tuple(sources or DEFAULT_BRACKET_PACK_RESOURCES)
    packs = [load_rule_pack(source) for source in selected_sources]
    seen_pack_ids: set[str] = set()
    seen_rule_ids: set[str] = set()
    for pack in packs:
        if pack.pack_id in seen_pack_ids:
            raise ValueError(f"duplicate rule pack id: {pack.pack_id}")
        seen_pack_ids.add(pack.pack_id)
        for rule in pack.rules:
            if rule.id in seen_rule_ids:
                raise ValueError(f"duplicate rule id across rule packs: {rule.id}")
            seen_rule_ids.add(rule.id)

    if not include_deprecated:
        packs = [pack for pack in packs if pack.status == "active"]
    return packs


def load_default_bracket_rule_packs(*, include_deprecated: bool = False) -> list[RulePack]:
    """Load the default bracket engineering rule packs."""

    return load_rule_packs(DEFAULT_BRACKET_PACK_RESOURCES, include_deprecated=include_deprecated)
