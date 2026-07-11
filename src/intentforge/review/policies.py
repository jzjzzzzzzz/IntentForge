"""Packaged declarative engineering review policy loading and lookup."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any, Iterable

import yaml

from intentforge.review.schema import ReviewPolicy, ReviewPolicyManifest


POLICY_RESOURCE_PACKAGE = "intentforge.review.data"
POLICY_RESOURCE_NAME = "review_policies.yaml"


class ReviewPolicyError(ValueError):
    """Raised when packaged review policy data is malformed or unavailable."""


def _read_policy_data(path: str | Path | None = None) -> dict[str, Any]:
    try:
        if path is None:
            text = resources.files(POLICY_RESOURCE_PACKAGE).joinpath(POLICY_RESOURCE_NAME).read_text(encoding="utf-8")
        else:
            text = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except (OSError, ModuleNotFoundError, yaml.YAMLError) as exc:
        raise ReviewPolicyError(f"could not load review policy manifest: {exc}") from exc
    if not isinstance(data, dict):
        raise ReviewPolicyError("review policy manifest must contain a mapping")
    return data


def load_review_policy_manifest(path: str | Path | None = None) -> ReviewPolicyManifest:
    """Load and schema-validate the packaged or supplied policy manifest."""

    try:
        return ReviewPolicyManifest.model_validate(_read_policy_data(path))
    except ValueError as exc:
        if isinstance(exc, ReviewPolicyError):
            raise
        raise ReviewPolicyError(f"invalid review policy manifest: {exc}") from exc


def load_review_policies(path: str | Path | None = None) -> list[ReviewPolicy]:
    """Return policies in stable policy-ID order."""

    return sorted(load_review_policy_manifest(path).policies, key=lambda item: item.policy_id)


class ReviewPolicyRegistry:
    """Deterministic registry for validated review policies."""

    def __init__(self, policies: Iterable[ReviewPolicy]):
        ordered = sorted(list(policies), key=lambda item: item.policy_id)
        ids = [policy.policy_id for policy in ordered]
        if len(ids) != len(set(ids)):
            raise ReviewPolicyError("duplicate review policy ids")
        self._policies = ordered
        self._by_id = {policy.policy_id: policy for policy in ordered}

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ReviewPolicyRegistry":
        return cls(load_review_policies(path))

    def all(self) -> list[ReviewPolicy]:
        return list(self._policies)

    def get(self, policy_id: str) -> ReviewPolicy:
        try:
            return self._by_id[policy_id]
        except KeyError as exc:
            raise ReviewPolicyError(f"unknown review policy: {policy_id}") from exc

    def count(self) -> int:
        return len(self._policies)


def get_review_policy(policy_id: str, path: str | Path | None = None) -> ReviewPolicy:
    return ReviewPolicyRegistry.load(path).get(policy_id)


def inspect_review_policy(policy_id: str, path: str | Path | None = None) -> dict[str, Any]:
    return get_review_policy(policy_id, path).model_dump(mode="json", serialize_as_any=True)
