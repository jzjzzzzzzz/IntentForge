"""Packaged fallback example data for installed IntentForge wheels."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from intentforge.paths import examples_dir


def _development_example_path(filename: str) -> Path | None:
    path = examples_dir() / filename
    return path if path.exists() else None


def read_example_text(filename: str) -> str:
    """Read an example file from a repo checkout or packaged wheel data."""

    development_path = _development_example_path(filename)
    if development_path is not None:
        return development_path.read_text(encoding="utf-8")

    return resources.files(__package__).joinpath(filename).read_text(encoding="utf-8")


def load_example_json(filename: str) -> dict[str, Any]:
    return json.loads(read_example_text(filename))


def load_example_yaml(filename: str) -> dict[str, Any]:
    return yaml.safe_load(read_example_text(filename))
