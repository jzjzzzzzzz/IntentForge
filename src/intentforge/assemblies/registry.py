"""Package-resource registry for declarative assembly manifests."""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from typing import Iterable

import yaml

from intentforge.assemblies.schema import AssemblyManifest
from intentforge.topology.expressions import expression_names

KNOWN_ASSEMBLY_FACTORY_IDS = {"flange_bolted_joint_factory_v1"}


class AssemblyRegistryError(ValueError):
    pass


def _validate_binding_reference(
    reference: str,
    components: dict[str, str],
    topology_parameters: dict[str, set[str]],
) -> None:
    parts = reference.split(".")
    if len(parts) != 2 or parts[0] not in components:
        raise AssemblyRegistryError(f"invalid assembly parameter binding: {reference}")
    family = components[parts[0]]
    if parts[1] not in topology_parameters.get(family, set()):
        raise AssemblyRegistryError(f"unknown topology parameter binding: {reference}")


class AssemblyRegistry:
    def __init__(
        self,
        manifests: Iterable[AssemblyManifest],
        *,
        topology_parameters: dict[str, set[str]],
    ):
        ordered = tuple(sorted(manifests, key=lambda item: item.assembly_family))
        families = [item.assembly_family for item in ordered]
        if len(families) != len(set(families)):
            raise AssemblyRegistryError("duplicate assembly family")
        aliases: dict[str, str] = {}
        for manifest in ordered:
            if manifest.assembly_factory_id not in KNOWN_ASSEMBLY_FACTORY_IDS:
                raise AssemblyRegistryError(f"unknown assembly factory adapter: {manifest.assembly_factory_id}")
            components = {item.component_id: item.topology_family for item in manifest.components}
            unknown_families = sorted(set(components.values()) - set(topology_parameters))
            if unknown_families:
                raise AssemblyRegistryError("unknown component topology families: " + ", ".join(unknown_families))
            for component in manifest.components:
                if component.quantity_expression is not None:
                    names = expression_names(component.quantity_expression)
                    if names != set(component.quantity_bindings):
                        raise AssemblyRegistryError(f"quantity bindings do not match expression for {component.component_id}")
                    for reference in component.quantity_bindings.values():
                        _validate_binding_reference(reference, components, topology_parameters)
            for constraint in manifest.spatial_constraints:
                names = expression_names(constraint.left_expression) | expression_names(constraint.right_expression)
                if names != set(constraint.variable_bindings):
                    raise AssemblyRegistryError(f"constraint bindings do not match expression for {constraint.constraint_id}")
                for reference in constraint.variable_bindings.values():
                    _validate_binding_reference(reference, components, topology_parameters)
            for alias in [manifest.assembly_family, *manifest.aliases]:
                key = alias.strip().lower()
                if key in aliases and aliases[key] != manifest.assembly_family:
                    raise AssemblyRegistryError(f"duplicate assembly alias: {alias}")
                aliases[key] = manifest.assembly_family
        self._manifests = ordered
        self._by_family = {item.assembly_family: item for item in ordered}
        self._aliases = aliases

    @classmethod
    def load(cls, *, topology_parameters: dict[str, set[str]] | None = None) -> "AssemblyRegistry":
        if topology_parameters is None:
            from intentforge.topology.registry import get_topology_registry

            topology_parameters = {
                item.topology_family: {parameter.name for parameter in item.controlled_parameters}
                for item in get_topology_registry().all(active_only=True)
            }
        root = files("intentforge").joinpath("knowledge", "assemblies")
        manifests: list[AssemblyManifest] = []
        for assembly_dir in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
            resource = assembly_dir.joinpath("manifest.yaml")
            if not resource.is_file():
                continue
            try:
                manifests.append(AssemblyManifest.model_validate(yaml.safe_load(resource.read_text(encoding="utf-8"))))
            except Exception as exc:
                raise AssemblyRegistryError(f"invalid assembly manifest {assembly_dir.name}/manifest.yaml: {exc}") from exc
        if not manifests:
            raise AssemblyRegistryError("no packaged assembly manifests were found")
        return cls(manifests, topology_parameters=topology_parameters)

    def all(self, *, active_only: bool = False) -> tuple[AssemblyManifest, ...]:
        return tuple(item for item in self._manifests if item.status == "active") if active_only else self._manifests

    def get(self, family: str) -> AssemblyManifest:
        resolved = self._aliases.get(family.strip().lower())
        if resolved is None or resolved not in self._by_family:
            raise AssemblyRegistryError(f"unregistered assembly family: {family}")
        manifest = self._by_family[resolved]
        if manifest.status != "active":
            raise AssemblyRegistryError(f"assembly family is not active: {resolved}")
        return manifest

    def count(self) -> int:
        return len(self._manifests)

    def snapshot(self) -> list[dict]:
        return [item.model_dump(mode="json") for item in self._manifests]


@lru_cache(maxsize=1)
def get_assembly_registry() -> AssemblyRegistry:
    return AssemblyRegistry.load()
