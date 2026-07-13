"""Deterministic package-resource loader for topology manifests."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Any, Iterable

import yaml

from intentforge.topology.expressions import expression_names
from intentforge.topology.schema import TopologyManifest


KNOWN_PARSER_IDS = {"legacy_wall_bracket_v1", "legacy_l_bracket_v1", "manifest_parameter_parser_v1"}
KNOWN_FACTORY_IDS = {"wall_bracket_factory_v1", "l_bracket_factory_v1", "industrial_flange_factory_v1"}
KNOWN_VALIDATOR_IDS = {"wall_bracket_validator_v1", "l_bracket_validator_v1", "industrial_flange_validator_v1"}


class TopologyRegistryError(ValueError):
    pass


class RegistryManager:
    """Immutable registry built from packaged, schema-validated manifests."""

    def __init__(self, manifests: Iterable[TopologyManifest]):
        ordered = tuple(sorted(manifests, key=lambda item: item.topology_family))
        families = [item.topology_family for item in ordered]
        if len(families) != len(set(families)):
            raise TopologyRegistryError("duplicate topology family")
        aliases: dict[str, str] = {}
        for manifest in ordered:
            if manifest.parser_id not in KNOWN_PARSER_IDS:
                raise TopologyRegistryError(f"unknown parser adapter: {manifest.parser_id}")
            if manifest.geometry_factory_id not in KNOWN_FACTORY_IDS:
                raise TopologyRegistryError(f"unknown geometry factory adapter: {manifest.geometry_factory_id}")
            if manifest.validator_id not in KNOWN_VALIDATOR_IDS:
                raise TopologyRegistryError(f"unknown validator adapter: {manifest.validator_id}")
            parameter_names = {item.name for item in manifest.controlled_parameters}
            for mapping in manifest.capability_evidence_binding.rule_variable_mapping:
                unknown = sorted(expression_names(mapping.expression) - parameter_names)
                if unknown:
                    raise TopologyRegistryError(
                        f"{manifest.topology_family}.{mapping.metric} references unknown variables: {', '.join(unknown)}"
                    )
            for alias in [manifest.topology_family, *manifest.aliases]:
                key = alias.strip().lower()
                if key in aliases and aliases[key] != manifest.topology_family:
                    raise TopologyRegistryError(f"duplicate topology alias: {alias}")
                aliases[key] = manifest.topology_family
        self._manifests = ordered
        self._by_family = {item.topology_family: item for item in ordered}
        self._aliases = aliases

    @classmethod
    def load(cls) -> "RegistryManager":
        root = files("intentforge").joinpath("knowledge", "topology", "families")
        manifests: list[TopologyManifest] = []
        for family_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
            resource = family_dir.joinpath("manifest.yaml")
            if not resource.is_file():
                continue
            try:
                raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
                manifests.append(TopologyManifest.model_validate(raw))
            except Exception as exc:
                raise TopologyRegistryError(f"invalid topology manifest {family_dir.name}/manifest.yaml: {exc}") from exc
        if not manifests:
            raise TopologyRegistryError("no packaged topology manifests were found")
        return cls(manifests)

    def all(self, *, active_only: bool = False) -> tuple[TopologyManifest, ...]:
        if active_only:
            return tuple(item for item in self._manifests if item.status == "active")
        return self._manifests

    def get(self, family: str) -> TopologyManifest:
        resolved = self._aliases.get(family.strip().lower())
        if resolved is None or resolved not in self._by_family:
            raise TopologyRegistryError(f"unregistered topology family: {family}")
        manifest = self._by_family[resolved]
        if manifest.status != "active":
            raise TopologyRegistryError(f"topology family is not active: {resolved}")
        return manifest

    def detect_family(self, text: str) -> str | None:
        normalized = " ".join(text.lower().replace("_", " ").split())
        matches: list[tuple[int, str]] = []
        for alias, family in self._aliases.items():
            normalized_alias = alias.replace("_", " ")
            if normalized_alias in normalized:
                matches.append((len(normalized_alias), family))
        return sorted(matches, key=lambda item: (-item[0], item[1]))[0][1] if matches else None

    def count(self) -> int:
        return len(self._manifests)

    def snapshot(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self._manifests]


@lru_cache(maxsize=1)
def get_topology_registry() -> RegistryManager:
    return RegistryManager.load()


def registered_family_ids() -> tuple[str, ...]:
    return tuple(item.topology_family for item in get_topology_registry().all(active_only=True))
