"""Typed schemas for declarative enterprise exemption ledgers (Phase 31).

An ``ExemptionManifest`` is a deterministic declaration that allows a specific
blocking policy finding to be acknowledged rather than enforced during a review
evaluation. The manifest is content-addressed by the ``exemption_hash`` field,
immutable once published, and consumed by the review engine via the
``policy_acknowledgement_required`` condition type.

Exemptions are an opt-in mitigation, not a bypass: when a manifest matches a
blocking finding, the deterministic precedence logic elevates
``rejected_by_policy`` to the new ``accepted_with_exemption`` status. The
manifest itself is fully ingested into the CAS envelope of the audit package so
that any applied override cryptographically changes the package identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intentforge.assurance.schema import validate_content_address


EXEMPTION_SCHEMA_VERSION = "1.0"
EXEMPTION_CONDITION_TYPE = "policy_acknowledgement_required"
SUPPORTED_EXEMPTION_TARGET_KINDS = ("rule_id", "metric", "parameter")
SUPPORTED_EXEMPTION_COMPARATORS = ("eq", "lt", "le", "gt", "ge")


ExemptionTargetKind = Literal["rule_id", "metric", "parameter"]
ExemptionComparator = Literal["eq", "lt", "le", "gt", "ge"]

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_NONCE_PATTERN = re.compile(r"^[a-zA-Z0-9._\-]{4,128}$")


def _hashable_comparator(comparator: str) -> str:
    if comparator not in SUPPORTED_EXEMPTION_COMPARATORS:
        raise ValueError(
            f"unsupported exemption comparator: {comparator!r}; "
            f"expected one of {', '.join(SUPPORTED_EXEMPTION_COMPARATORS)}"
        )
    return comparator


def _serialise_target_value(kind: str, value: Any) -> Any:
    if kind == "rule_id":
        return str(value)
    if kind == "metric":
        return str(value)
    if kind == "parameter":
        return str(value)
    raise ValueError(f"unsupported exemption target kind: {kind}")


class ExemptionTarget(BaseModel):
    """A single, fully-qualified target reference inside a blocking finding."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    kind: ExemptionTargetKind
    identifier: str = Field(..., min_length=1)
    comparator: ExemptionComparator = "eq"
    value: str | int | float | bool = "all"

    @field_validator("kind")
    @classmethod
    def known_kind(cls, value: str) -> str:
        if value not in SUPPORTED_EXEMPTION_TARGET_KINDS:
            raise ValueError(
                f"unsupported exemption target kind: {value!r}; "
                f"expected one of {', '.join(SUPPORTED_EXEMPTION_TARGET_KINDS)}"
            )
        return value

    @field_validator("comparator")
    @classmethod
    def known_comparator(cls, value: str) -> str:
        return _hashable_comparator(value)

    @field_validator("identifier")
    @classmethod
    def identifier_safe(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("exemption target identifier must be non-empty")
        if any(char in cleaned for char in {"\n", "\r", "\t"}):
            raise ValueError("exemption target identifier contains forbidden whitespace")
        return cleaned

    def to_hashable(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "identifier": self.identifier,
            "comparator": self.comparator,
            "value": _serialise_target_value(self.kind, self.value),
        }


class ExemptionManifest(BaseModel):
    """A deterministic enterprise exemption ledger entry.

    The manifest declares which blocking findings are eligible for override and
    records the governance metadata (rationale, authorizing entity, nonce, and
    immutable ``exemption_hash``) required to attribute the override to a known
    external authority.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: str = EXEMPTION_SCHEMA_VERSION
    exemption_id: str = Field(..., min_length=1)
    cad_family: str = Field(..., min_length=1)
    policy_id: str = Field(..., min_length=1)
    policy_version: str = Field(..., min_length=1)
    authorizing_entity: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    issued_at: str = Field(..., min_length=1)
    expires_at: str | None = None
    nonce: str = Field(..., min_length=4, max_length=128)
    targets: list[ExemptionTarget] = Field(..., min_length=1, max_length=64)
    exemption_hash: str = ""
    content_id: str = ""

    @field_validator("cad_family")
    @classmethod
    def known_family(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("exemption manifest requires a CAD family")
        return cleaned

    @field_validator("policy_id")
    @classmethod
    def known_policy_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("exemption manifest requires a policy id")
        return cleaned

    @field_validator("policy_version")
    @classmethod
    def known_policy_version(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("exemption manifest requires a policy version")
        return cleaned

    @field_validator("nonce")
    @classmethod
    def valid_nonce(cls, value: str) -> str:
        if not _NONCE_PATTERN.fullmatch(value):
            raise ValueError("exemption nonce must be 4-128 chars of [A-Za-z0-9._-]")
        return value

    @field_validator("targets")
    @classmethod
    def min_targets(cls, value: list[ExemptionTarget]) -> list[ExemptionTarget]:
        if not value:
            raise ValueError("exemption manifest must declare at least one target")
        return value

    @model_validator(mode="after")
    def validate_identifier(self) -> "ExemptionManifest":
        unique = {(item.kind, item.identifier, item.comparator) for item in self.targets}
        if len(unique) != len(self.targets):
            raise ValueError("exemption manifest contains duplicate targets")
        expected_hash = _compute_exemption_hash(self)
        expected_content = _compute_exemption_content_id(self)
        if self.exemption_hash and self.exemption_hash != expected_hash:
            raise ValueError("exemption hash does not match immutable content")
        if self.content_id and self.content_id != expected_content:
            raise ValueError("exemption content id does not match immutable content")
        if not self.exemption_hash:
            object.__setattr__(self, "exemption_hash", expected_hash)
        if not self.content_id:
            object.__setattr__(self, "content_id", expected_content)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        """Return the manifest body used for hashing and CAS ingestion."""

        data = self.model_dump(mode="json")
        data.pop("exemption_hash", None)
        data.pop("content_id", None)
        data["targets"] = sorted(
            [target.to_hashable() for target in self.targets],
            key=lambda item: (item["kind"], item["identifier"], item["comparator"]),
        )
        return data

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _compute_exemption_hash(manifest: ExemptionManifest) -> str:
    payload = manifest.deterministic_payload()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_exemption_content_id(manifest: ExemptionManifest) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(
            manifest.deterministic_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


class ExemptionManifestValidationResult(BaseModel):
    """Validation summary for a single declarative exemption manifest."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    manifest_id: str | None = None
    exemption_hash: str | None = None
    content_id: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)


def validate_exemption_manifest(manifest: ExemptionManifest | dict[str, Any]) -> ExemptionManifestValidationResult:
    """Validate a manifest for content-addressable identity and metadata rules."""

    errors: list[str] = []
    warnings: list[str] = []
    try:
        record = manifest if isinstance(manifest, ExemptionManifest) else ExemptionManifest.model_validate(manifest)
    except (ValueError, TypeError) as exc:
        return ExemptionManifestValidationResult(passed=False, errors=[str(exc)])
    if not _HASH_PATTERN.fullmatch(record.exemption_hash or ""):
        errors.append("exemption_hash must use sha256:<64 lowercase hex chars>")
    if not validate_content_address(record.exemption_hash):
        errors.append("exemption_hash failed canonical content-address validation")
    if record.expires_at is not None and record.expires_at.strip() == "":
        warnings.append("expires_at is empty; treating as never-expiring manifest")
    return ExemptionManifestValidationResult(
        passed=not errors,
        manifest_id=record.exemption_id,
        exemption_hash=record.exemption_hash,
        content_id=record.content_id,
        errors=errors,
        warnings=warnings,
        metrics={
            "target_count": len(record.targets),
            "rule_target_count": sum(1 for t in record.targets if t.kind == "rule_id"),
            "metric_target_count": sum(1 for t in record.targets if t.kind == "metric"),
            "parameter_target_count": sum(1 for t in record.targets if t.kind == "parameter"),
        },
    )


class ExemptionLedger(BaseModel):
    """An immutable ordered collection of exemption manifests."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: str = EXEMPTION_SCHEMA_VERSION
    ledger_id: str = Field(..., min_length=1)
    cad_family: str = Field(..., min_length=1)
    policy_id: str = Field(..., min_length=1)
    policy_version: str = Field(..., min_length=1)
    manifests: list[ExemptionManifest] = Field(default_factory=list)
    content_address: str = ""

    @field_validator("manifests")
    @classmethod
    def unique_manifests(cls, value: list[ExemptionManifest]) -> list[ExemptionManifest]:
        seen: set[str] = set()
        for item in value:
            if item.exemption_id in seen:
                raise ValueError(f"duplicate exemption_id in ledger: {item.exemption_id}")
            seen.add(item.exemption_id)
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> "ExemptionLedger":
        ordered = sorted(self.manifests, key=lambda item: item.exemption_id)
        if self.manifests != ordered:
            object.__setattr__(self, "manifests", ordered)
        expected = _compute_ledger_address(self)
        if self.content_address and self.content_address != expected:
            raise ValueError("exemption ledger content address mismatch")
        if not self.content_address:
            object.__setattr__(self, "content_address", expected)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ledger_id": self.ledger_id,
            "cad_family": self.cad_family,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "manifests": [item.exemption_hash for item in self.manifests],
        }

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def _compute_ledger_address(ledger: ExemptionLedger) -> str:
    canonical = json.dumps(
        ledger.deterministic_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AppliedExemptionReference(BaseModel):
    """The deterministic record of a single applied exemption inside a decision."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    reference_id: str = Field(..., min_length=1)
    exemption_id: str = Field(..., min_length=1)
    exemption_hash: str = Field(..., min_length=1)
    applying_entity: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    matched_check_id: str = Field(..., min_length=1)
    matched_rule_ids: list[str] = Field(default_factory=list)
    matched_metric_ids: list[str] = Field(default_factory=list)
    matched_parameter_ids: list[str] = Field(default_factory=list)
    content_id: str = ""

    @field_validator("exemption_hash")
    @classmethod
    def valid_hash(cls, value: str) -> str:
        if not value.startswith("sha256:") or len(value) != len("sha256:") + 64:
            raise ValueError("applied exemption exemption_hash must use sha256:<64 hex>")
        return value

    @model_validator(mode="after")
    def compute_identity(self) -> "AppliedExemptionReference":
        payload = self.model_dump(mode="json")
        if payload.get("content_id"):
            return self
        canonical = json.dumps(
            {
                "exemption_id": payload["exemption_id"],
                "exemption_hash": payload["exemption_hash"],
                "matched_check_id": payload["matched_check_id"],
                "matched_rule_ids": sorted(payload.get("matched_rule_ids", [])),
                "matched_metric_ids": sorted(payload.get("matched_metric_ids", [])),
                "matched_parameter_ids": sorted(payload.get("matched_parameter_ids", [])),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        content_id = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        object.__setattr__(self, "content_id", content_id)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data.pop("content_id", None)
        return data


class ExemptionEvaluation(BaseModel):
    """Aggregate outcome of evaluating a set of manifests against a decision."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: str = EXEMPTION_SCHEMA_VERSION
    decision_id: str = Field(..., min_length=1)
    elevated_to_exemption: bool = False
    applied_references: list[AppliedExemptionReference] = Field(default_factory=list)
    unmatched_manifest_ids: list[str] = Field(default_factory=list)
    content_address: str = ""

    @model_validator(mode="after")
    def compute_content_address(self) -> "ExemptionEvaluation":
        payload = {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "elevated_to_exemption": self.elevated_to_exemption,
            "applied_references": [item.content_id for item in self.applied_references],
            "unmatched_manifest_ids": sorted(self.unmatched_manifest_ids),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        expected = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if self.content_address and self.content_address != expected:
            raise ValueError("exemption evaluation content address mismatch")
        if not self.content_address:
            object.__setattr__(self, "content_address", expected)
        return self

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


__all__ = [
    "EXEMPTION_CONDITION_TYPE",
    "AppliedExemptionReference",
    "ExemptionComparator",
    "ExemptionEvaluation",
    "ExemptionLedger",
    "ExemptionManifest",
    "ExemptionManifestValidationResult",
    "ExemptionTarget",
    "ExemptionTargetKind",
    "apply_exemptions_to_decision",
    "evaluate_exemption_for_finding",
    "load_exemption_manifest",
    "match_exemptions",
    "validate_exemption_manifest",
]
