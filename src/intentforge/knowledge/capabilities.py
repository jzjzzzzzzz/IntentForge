"""Capability manifest loading for IntentForge engineering coverage."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from intentforge.knowledge.capability_schema import CapabilityDefinition, CapabilityManifest


DEFAULT_CAPABILITY_MANIFEST_RESOURCE = "capability_manifest.yaml"


class CapabilityManifestError(ValueError):
    """Raised when a capability manifest cannot be loaded or validated."""


def _read_manifest_yaml(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        text = resources.files("intentforge.knowledge.data").joinpath(
            DEFAULT_CAPABILITY_MANIFEST_RESOURCE
        ).read_text(encoding="utf-8")
    else:
        source_path = Path(path)
        text = source_path.read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    if not isinstance(raw, dict):
        raise CapabilityManifestError("capability manifest must contain a YAML mapping")
    return raw


def load_capability_manifest(path: str | Path | None = None) -> CapabilityManifest:
    """Load the packaged or user-provided capability manifest."""

    try:
        return CapabilityManifest.model_validate(_read_manifest_yaml(path))
    except ValidationError as exc:
        raise CapabilityManifestError(str(exc)) from exc


def load_capabilities(path: str | Path | None = None) -> list[CapabilityDefinition]:
    """Load capabilities in deterministic manifest order."""

    return load_capability_manifest(path).capabilities
