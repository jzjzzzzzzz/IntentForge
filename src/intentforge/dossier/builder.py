"""Release dossier aggregator: multi-component Merkle-rooted release qualification."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from intentforge.dossier.merkle import (
    MERKLE_TREE_VERSION,
    MerkleTree,
    build_merkle_tree,
)
from intentforge.offline_verify import (
    CAS_ENVELOPE_FILE,
    verify_offline_audit_package,
)
from intentforge.redaction.verifier import (
    REDACTED_ENVELOPE_FILE as REDACTION_ENVELOPE_FILE_NAME,
    verify_redacted_audit_package,
)


DOSSIER_SCHEMA_VERSION = "1.0"
DOSSIER_ENVELOPE_FILE = "dossier_envelope.json"
DOSSIER_ROLLUP_FILE = "dossier_rollup.json"
DOSSIER_MANIFEST_FILE = "dossier_manifest.json"
DOSSIER_CHECKSUMS_FILE = "dossier_checksums.json"
DOSSIER_LEAF_INDEX_FILE = "dossier_leaf_index.json"

DossierRollupStatus = str

ROLLOUP_STATUS_APPROVED = "release_approved"
ROLLOUP_STATUS_APPROVED_WITH_CONDITIONS = "release_approved_with_conditions"
ROLLOUP_STATUS_BLOCKED = "release_blocked"

_BLOCKING_CHILD_STATUSES = {"rejected_by_policy", "unresolved"}
_CONDITIONAL_CHILD_STATUSES = {"accepted_with_conditions", "manual_review_required", "accepted_with_exemption"}
_APPROVED_CHILD_STATUSES = {"accepted_within_declared_scope"}


def validate_cas_address(value: str) -> str:
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)):
        raise ValueError("content address must use sha256:<64 lowercase hex characters>")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_address(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_redacted_package(package_dir: Path) -> bool:
    return (package_dir / REDACTION_ENVELOPE_FILE_NAME).is_file()


def _resolve_child_content_address(package_dir: Path) -> str | None:
    redacted_envelope_path = package_dir / REDACTION_ENVELOPE_FILE_NAME
    if redacted_envelope_path.is_file():
        try:
            envelope = json.loads(redacted_envelope_path.read_text(encoding="utf-8"))
            address = envelope.get("content_address")
            if isinstance(address, str):
                return validate_cas_address(address)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
    cas_envelope_path = package_dir / CAS_ENVELOPE_FILE
    if cas_envelope_path.is_file():
        try:
            envelope = json.loads(cas_envelope_path.read_text(encoding="utf-8"))
            address = envelope.get("content_address")
            if isinstance(address, str):
                return validate_cas_address(address)
        except (OSError, json.JSONDecodeError, ValueError):
            return None
    return None


def _resolve_child_decision_status(package_dir: Path) -> str | None:
    decision_path = package_dir / "review_decision.json"
    if not decision_path.is_file():
        return None
    try:
        decision = json.loads(decision_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return decision.get("decision_status")


def _resolve_child_assurance_case_id(package_dir: Path) -> str | None:
    case_path = package_dir / "assurance_case.json"
    if not case_path.is_file():
        return None
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return case.get("assurance_case_id")


@dataclass(frozen=True)
class DossierLeaf:
    """A single child audit package registered with a release dossier."""

    leaf_id: str
    package_path: str
    content_address: str
    package_kind: str
    assurance_case_id: str | None
    review_decision_id: str | None
    cad_family: str | None
    operation: str | None
    decision_status: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "leaf_id": self.leaf_id,
            "package_path": self.package_path,
            "content_address": self.content_address,
            "package_kind": self.package_kind,
            "assurance_case_id": self.assurance_case_id,
            "review_decision_id": self.review_decision_id,
            "cad_family": self.cad_family,
            "operation": self.operation,
            "decision_status": self.decision_status,
        }


@dataclass(frozen=True)
class DossierRollup:
    """Deterministic compliance rollup for a release dossier."""

    rollup_status: str
    child_count: int
    blocked_count: int
    conditional_count: int
    approved_count: int
    other_count: int
    leaf_summaries: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollup_status": self.rollup_status,
            "child_count": self.child_count,
            "blocked_count": self.blocked_count,
            "conditional_count": self.conditional_count,
            "approved_count": self.approved_count,
            "other_count": self.other_count,
            "leaf_summaries": list(self.leaf_summaries),
        }


def compute_dossier_rollup(leaves: tuple[DossierLeaf, ...]) -> DossierRollup:
    """Compute deterministic rollup status from registered leaves.

    Precedence:
      * any blocking child (``rejected_by_policy``, ``unresolved``) ⇒ ``release_blocked``
      * otherwise any conditional child (``accepted_with_conditions``,
        ``manual_review_required``, ``accepted_with_exemption``) ⇒
        ``release_approved_with_conditions``.

        Per Phase 31, ``accepted_with_exemption`` overrides are bucketed with
        conditional approval: the release is allowed but the cryptographic
        exemption references remain visible in the audit trail.

      * otherwise ``release_approved`` when every child is approved;
        missing or unknown statuses contribute to ``other_count`` but
        do not flip the rollup to blocked once approved children exist.
    """

    blocked = conditional = approved = other = 0
    leaf_summaries: list[dict[str, Any]] = []
    for leaf in leaves:
        status = leaf.decision_status
        if status in _BLOCKING_CHILD_STATUSES:
            blocked += 1
        elif status in _CONDITIONAL_CHILD_STATUSES:
            conditional += 1
        elif status in _APPROVED_CHILD_STATUSES:
            approved += 1
        else:
            other += 1
        leaf_summaries.append({
            "leaf_id": leaf.leaf_id,
            "content_address": leaf.content_address,
            "cad_family": leaf.cad_family,
            "operation": leaf.operation,
            "decision_status": status,
        })

    if blocked > 0:
        rollup = ROLLOUP_STATUS_BLOCKED
    elif conditional > 0:
        rollup = ROLLOUP_STATUS_APPROVED_WITH_CONDITIONS
    elif approved > 0 and other == 0:
        rollup = ROLLOUP_STATUS_APPROVED
    elif approved > 0:
        rollup = ROLLOUP_STATUS_APPROVED_WITH_CONDITIONS
    elif other == len(leaves) and len(leaves) > 0:
        rollup = ROLLOUP_STATUS_BLOCKED
    else:
        rollup = ROLLOUP_STATUS_BLOCKED

    return DossierRollup(
        rollup_status=rollup,
        child_count=len(leaves),
        blocked_count=blocked,
        conditional_count=conditional,
        approved_count=approved,
        other_count=other,
        leaf_summaries=tuple(leaf_summaries),
    )


@dataclass(frozen=True)
class ReleaseDossier:
    """Cryptographic Merkle-rooted multi-component release dossier."""

    dossier_id: str
    schema_version: str
    leaves: tuple[DossierLeaf, ...]
    merkle_tree: MerkleTree
    rollup: DossierRollup
    dossier_envelope: dict[str, Any] = field(default_factory=dict)

    @property
    def root_hash(self) -> str | None:
        return self.merkle_tree.root_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "dossier_id": self.dossier_id,
            "schema_version": self.schema_version,
            "root_hash": self.root_hash,
            "leaf_count": self.merkle_tree.leaf_count,
            "leaves": [leaf.to_dict() for leaf in self.leaves],
            "merkle_tree": self.merkle_tree.to_dict(),
            "rollup": self.rollup.to_dict(),
            "dossier_envelope": dict(sorted(self.dossier_envelope.items())),
        }


class ReleaseDossierBuilder:
    """Builds a ReleaseDossier from a list of audit package directories."""

    def __init__(self, *, dossier_id: str | None = None):
        self._explicit_dossier_id = dossier_id

    def build(self, package_paths: list[str | Path]) -> ReleaseDossier:
        """Build a release dossier from the supplied audit package directories."""

        if not package_paths:
            raise ValueError("at least one audit package directory is required")

        leaves: list[DossierLeaf] = []
        seen_addresses: set[str] = set()
        for index, raw_path in enumerate(package_paths):
            path = Path(raw_path)
            if not path.is_dir():
                raise ValueError(f"audit package directory does not exist: {path}")
            content_address = _resolve_child_content_address(path)
            if content_address is None:
                raise ValueError(
                    f"audit package at {path} is missing a CAS or redacted envelope"
                )
            if content_address in seen_addresses:
                raise ValueError(
                    f"duplicate child content address in dossier: {content_address}"
                )
            seen_addresses.add(content_address)
            package_kind = "redacted" if _is_redacted_package(path) else "standard"
            case_id = _resolve_child_assurance_case_id(path)
            decision_status = _resolve_child_decision_status(path)
            decision_id: str | None = None
            decision_path = path / "review_decision.json"
            if decision_path.is_file():
                try:
                    decision_doc = json.loads(decision_path.read_text(encoding="utf-8"))
                    decision_id = decision_doc.get("decision_id")
                    cad_family = decision_doc.get("subject_type") or None
                except (OSError, json.JSONDecodeError):
                    decision_id = None
                    cad_family = None
            else:
                cad_family = None
            envelope_for_meta: dict[str, Any] = {}
            env_path = path / (REDACTION_ENVELOPE_FILE_NAME if package_kind == "redacted" else CAS_ENVELOPE_FILE)
            if env_path.is_file():
                try:
                    envelope_for_meta = json.loads(env_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    envelope_for_meta = {}
            cad_family = (
                envelope_for_meta.get("cad_family")
                or _resolve_case_field(path, "cad_family")
                or None
            )
            operation = (
                envelope_for_meta.get("operation")
                or _resolve_case_field(path, "operation")
                or None
            )
            leaf_id = f"leaf_{index:04d}"
            leaves.append(DossierLeaf(
                leaf_id=leaf_id,
                package_path=str(path),
                content_address=content_address,
                package_kind=package_kind,
                assurance_case_id=case_id,
                review_decision_id=decision_id,
                cad_family=cad_family,
                operation=operation,
                decision_status=decision_status,
            ))

        merkle_tree = build_merkle_tree(tuple(leaf.content_address for leaf in leaves))
        rollup = compute_dossier_rollup(tuple(leaves))

        dossier_id = self._explicit_dossier_id or _derive_dossier_id(merkle_tree.root_hash)

        envelope: dict[str, Any] = {
            "schema_version": DOSSIER_SCHEMA_VERSION,
            "hash_algorithm": "sha256",
            "merkle_tree_version": MERKLE_TREE_VERSION,
            "dossier_id": dossier_id,
            "root_hash": merkle_tree.root_hash,
            "leaf_count": merkle_tree.leaf_count,
            "rollup_status": rollup.rollup_status,
            "leaf_addresses": [leaf.content_address for leaf in leaves],
            "leaf_identifiers": [
                {"leaf_id": leaf.leaf_id, "content_address": leaf.content_address}
                for leaf in leaves
            ],
        }
        envelope["content_address"] = _sha256_address(envelope)

        return ReleaseDossier(
            dossier_id=dossier_id,
            schema_version=DOSSIER_SCHEMA_VERSION,
            leaves=tuple(leaves),
            merkle_tree=merkle_tree,
            rollup=rollup,
            dossier_envelope=envelope,
        )


def _derive_dossier_id(root_hash: str | None) -> str:
    if root_hash is None:
        return "dossier_empty"
    return f"dossier_{root_hash[:16]}"


def _resolve_case_field(package_dir: Path, field_name: str) -> str | None:
    case_path = package_dir / "assurance_case.json"
    if not case_path.is_file():
        return None
    try:
        case = json.loads(case_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = case.get(field_name)
    return value if isinstance(value, str) else None


def build_dossier(package_paths: list[str | Path]) -> ReleaseDossier:
    """Convenience function to build a release dossier from package paths."""

    return ReleaseDossierBuilder().build(package_paths)


def write_dossier(dossier: ReleaseDossier, output_dir: str | Path) -> dict[str, Any]:
    """Write the dossier artifacts into ``output_dir``.

    Returns a summary dictionary describing the written files.
    """

    output = Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        shutil.rmtree(output)

    envelope_payload = _canonical_json_bytes(dossier.dossier_envelope)
    rollup_payload = _canonical_json_bytes(dossier.rollup.to_dict())
    leaf_index_payload = _canonical_json_bytes([
        leaf.to_dict() for leaf in dossier.leaves
    ])
    merkle_payload = _canonical_json_bytes(dossier.merkle_tree.to_dict())

    other_files: dict[str, bytes] = {
        DOSSIER_ENVELOPE_FILE: envelope_payload,
        DOSSIER_ROLLUP_FILE: rollup_payload,
        DOSSIER_LEAF_INDEX_FILE: leaf_index_payload,
        "dossier_merkle_tree.json": merkle_payload,
    }

    final_checksums: dict[str, str] = {
        name: _sha256(data) for name, data in sorted(other_files.items())
    }

    manifest_payload = _build_dossier_manifest(
        dossier, file_inventory=dict(final_checksums),
    )
    final_checksums[DOSSIER_MANIFEST_FILE] = _sha256(manifest_payload)

    final_files: dict[str, bytes] = dict(other_files)
    final_files[DOSSIER_MANIFEST_FILE] = manifest_payload
    final_files[DOSSIER_CHECKSUMS_FILE] = _canonical_json_bytes(final_checksums)

    temporary = Path(tempfile.mkdtemp(prefix=".intentforge-dossier-"))
    try:
        for name, data in sorted(final_files.items()):
            (temporary / name).write_bytes(data)
        shutil.copytree(temporary, output)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)

    return {
        "dossier_id": dossier.dossier_id,
        "root_hash": dossier.root_hash,
        "rollup_status": dossier.rollup.rollup_status,
        "leaf_count": dossier.merkle_tree.leaf_count,
        "package_path": str(output),
        "file_count": len(final_files),
    }


def _build_dossier_manifest(
    dossier: ReleaseDossier,
    *,
    file_inventory: dict[str, str] | None = None,
) -> bytes:
    inventory = file_inventory or {}
    manifest = {
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "dossier_id": dossier.dossier_id,
        "root_hash": dossier.root_hash,
        "rollup_status": dossier.rollup.rollup_status,
        "merkle_tree_version": MERKLE_TREE_VERSION,
        "leaf_count": dossier.merkle_tree.leaf_count,
        "blocked_count": dossier.rollup.blocked_count,
        "conditional_count": dossier.rollup.conditional_count,
        "approved_count": dossier.rollup.approved_count,
        "file_inventory": inventory,
    }
    return _canonical_json_bytes(manifest)


__all__ = [
    "DOSSIER_SCHEMA_VERSION",
    "ROLLOUP_STATUS_APPROVED",
    "ROLLOUP_STATUS_APPROVED_WITH_CONDITIONS",
    "ROLLOUP_STATUS_BLOCKED",
    "DossierLeaf",
    "DossierRollup",
    "ReleaseDossier",
    "ReleaseDossierBuilder",
    "build_dossier",
    "compute_dossier_rollup",
    "write_dossier",
]