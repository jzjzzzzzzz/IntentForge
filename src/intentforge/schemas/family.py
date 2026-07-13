"""Shared registered-family validation for structured CAD records."""

from __future__ import annotations


def validate_registered_family(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("family must be a non-empty string")
    from intentforge.topology.registry import get_topology_registry

    manifest = get_topology_registry().get(value)
    return manifest.topology_family
