"""Standard-library-only recursive verifier for release dossiers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from intentforge.dossier.merkle import (
    MERKLE_TREE_VERSION,
    rebuild_merkle_root,
)
from intentforge.dossier.builder import (
    DOSSIER_CHECKSUMS_FILE,
    DOSSIER_ENVELOPE_FILE,
    DOSSIER_LEAF_INDEX_FILE,
    DOSSIER_SCHEMA_VERSION,
    DossierLeaf,
    compute_dossier_rollup,
    _sha256,
    validate_cas_address,
)
from intentforge.offline_verify import (
    verify_offline_audit_package,
)
from intentforge.redaction.verifier import (
    verify_redacted_audit_package,
)


DOSSIER_VERIFIER_VERSION = "1.0"


@dataclass(frozen=True)
class DossierChildVerification:
    """Result of verifying a single child audit package inside a dossier."""

    leaf_id: str
    content_address: str
    package_kind: str
    passed: bool
    status: str
    errors: tuple[str, ...] = ()
    offline_verification_passed: bool | None = None
    offline_package_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "leaf_id": self.leaf_id,
            "content_address": self.content_address,
            "package_kind": self.package_kind,
            "passed": self.passed,
            "status": self.status,
            "offline_verification_passed": self.offline_verification_passed,
            "offline_package_id": self.offline_package_id,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class DossierVerificationResult:
    """Verification result for a release dossier."""

    passed: bool
    status: str
    failure_stage: str | None = None
    dossier_id: str | None = None
    root_hash: str | None = None
    rollup_status: str | None = None
    child_count: int = 0
    passed_child_count: int = 0
    failed_child_count: int = 0
    child_verifications: tuple[DossierChildVerification, ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "status": self.status,
            "failure_stage": self.failure_stage,
            "dossier_id": self.dossier_id,
            "root_hash": self.root_hash,
            "rollup_status": self.rollup_status,
            "child_count": self.child_count,
            "passed_child_count": self.passed_child_count,
            "failed_child_count": self.failed_child_count,
            "child_verifications": [child.to_dict() for child in self.child_verifications],
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": dict(sorted(self.metrics.items())),
            "dossier_verifier_version": DOSSIER_VERIFIER_VERSION,
        }


def _load_json_bytes(data: bytes, name: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name}: invalid UTF-8: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name}: invalid JSON: {exc}") from exc


def _validate_envelope(envelope: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics: dict[str, Any] = {}

    allowed_keys = {
        "schema_version", "hash_algorithm", "merkle_tree_version",
        "dossier_id", "root_hash", "leaf_count", "rollup_status",
        "leaf_addresses", "leaf_identifiers", "content_address",
    }
    if set(envelope) != allowed_keys:
        errors.append("dossier envelope field set mismatch")
    if envelope.get("schema_version") != DOSSIER_SCHEMA_VERSION:
        errors.append("unsupported dossier envelope schema version")
    if envelope.get("hash_algorithm") != "sha256":
        errors.append("unsupported dossier hash algorithm")
    if envelope.get("merkle_tree_version") != MERKLE_TREE_VERSION:
        errors.append("unsupported merkle tree version")

    leaf_addresses = envelope.get("leaf_addresses")
    if not isinstance(leaf_addresses, list) or not leaf_addresses:
        errors.append("dossier envelope must contain at least one leaf address")
    else:
        for address in leaf_addresses:
            try:
                validate_cas_address(address)
            except ValueError as exc:
                errors.append(f"invalid leaf content address: {exc}")

    root_hash = envelope.get("root_hash")
    if root_hash is not None:
        try:
            validate_cas_address(root_hash)
        except ValueError as exc:
            errors.append(f"invalid root hash: {exc}")

    envelope_copy = dict(envelope)
    envelope_copy.pop("content_address", None)
    canonical = json.dumps(envelope_copy, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected_address = "sha256:" + _sha256(canonical.encode("utf-8"))
    if envelope.get("content_address") != expected_address:
        errors.append("dossier envelope content address mismatch")

    metrics["leaf_count_in_envelope"] = (
        len(leaf_addresses) if isinstance(leaf_addresses, list) else 0
    )
    metrics["envelope_hash_verified"] = envelope.get("content_address") == expected_address
    return errors, metrics


def _validate_leaf_index(
    leaf_index: list[dict[str, Any]],
    envelope: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics: dict[str, Any] = {}
    leaf_addresses = envelope.get("leaf_addresses", [])
    if not isinstance(leaf_addresses, list):
        leaf_addresses = []

    sorted_entries = sorted(leaf_index, key=lambda item: item.get("leaf_id", ""))
    sorted_addresses = [item.get("content_address") for item in sorted_entries]
    expected_addresses = list(leaf_addresses)
    if sorted_addresses != expected_addresses:
        errors.append("leaf index does not match envelope leaf_addresses")

    metrics["leaf_index_size"] = len(sorted_entries)
    return errors, metrics


def _validate_merkle_root(
    envelope: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics: dict[str, Any] = {}
    leaf_addresses = envelope.get("leaf_addresses", [])
    if not isinstance(leaf_addresses, list):
        errors.append("leaf_addresses is not a list")
        return errors, metrics
    expected_root = rebuild_merkle_root(tuple(leaf_addresses))
    actual_root = envelope.get("root_hash")
    if actual_root != expected_root:
        errors.append(
            f"recomputed merkle root mismatch: expected {expected_root}, got {actual_root}"
        )
    metrics["recomputed_merkle_root"] = expected_root
    metrics["merkle_root_verified"] = actual_root == expected_root
    return errors, metrics


def _validate_checksums(
    files: dict[str, bytes],
    checksums: dict[str, Any] | None,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics: dict[str, Any] = {}
    if not isinstance(checksums, dict):
        errors.append("dossier checksums must be a JSON object")
        return errors, metrics
    skip = {DOSSIER_CHECKSUMS_FILE}
    mismatches = 0
    for name, expected in checksums.items():
        if name in skip:
            continue
        if name not in files:
            errors.append(f"checksum references missing file: {name}")
            continue
        actual = _sha256(files[name])
        if actual != expected:
            errors.append(f"checksum mismatch: {name}")
            mismatches += 1
    metrics["hash_mismatch_count"] = mismatches
    metrics["checksum_validation_passed"] = mismatches == 0
    return errors, metrics


def _validate_rollup(
    envelope: dict[str, Any],
    leaf_index: list[dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    metrics: dict[str, Any] = {}
    leaves: list[DossierLeaf] = []
    for entry in leaf_index:
        leaves.append(DossierLeaf(
            leaf_id=entry.get("leaf_id", ""),
            package_path=entry.get("package_path", ""),
            content_address=entry.get("content_address", ""),
            package_kind=entry.get("package_kind", "standard"),
            assurance_case_id=entry.get("assurance_case_id"),
            review_decision_id=entry.get("review_decision_id"),
            cad_family=entry.get("cad_family"),
            operation=entry.get("operation"),
            decision_status=entry.get("decision_status"),
        ))
    expected_rollup = compute_dossier_rollup(tuple(leaves))
    if envelope.get("rollup_status") != expected_rollup.rollup_status:
        errors.append(
            f"rollup status mismatch: envelope says {envelope.get('rollup_status')}, "
            f"recomputed {expected_rollup.rollup_status}"
        )
    metrics["recomputed_rollup_status"] = expected_rollup.rollup_status
    metrics["blocked_count"] = expected_rollup.blocked_count
    metrics["conditional_count"] = expected_rollup.conditional_count
    metrics["approved_count"] = expected_rollup.approved_count
    return errors, metrics


def _resolve_child_package_paths(
    leaf_index: list[dict[str, Any]],
    dossier_dir: Path,
) -> list[Path]:
    paths: list[Path] = []
    for entry in leaf_index:
        raw = entry.get("package_path")
        if not isinstance(raw, str):
            paths.append(dossier_dir)
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = dossier_dir / raw
        paths.append(candidate)
    return paths


def _verify_child(
    leaf: dict[str, Any],
    package_path: Path,
) -> DossierChildVerification:
    """Verify a single child audit package using the offline verifier."""

    leaf_id = leaf.get("leaf_id", "")
    content_address = leaf.get("content_address", "")
    kind = leaf.get("package_kind", "standard")

    if not package_path.is_dir():
        return DossierChildVerification(
            leaf_id=leaf_id,
            content_address=content_address,
            package_kind=kind,
            passed=False,
            status="failed",
            errors=(f"child package directory missing: {package_path}",),
        )

    if kind == "redacted":
        result = verify_redacted_audit_package(package_path)
        return DossierChildVerification(
            leaf_id=leaf_id,
            content_address=content_address,
            package_kind=kind,
            passed=result.passed,
            status=result.status,
            errors=tuple(result.errors),
            offline_verification_passed=result.passed,
            offline_package_id=result.redacted_package_id or result.original_package_id,
        )

    result = verify_offline_audit_package(package_path)
    return DossierChildVerification(
        leaf_id=leaf_id,
        content_address=content_address,
        package_kind=kind,
        passed=result.passed,
        status=result.status,
        errors=tuple(result.errors),
        offline_verification_passed=result.passed,
        offline_package_id=result.package_id,
    )


def verify_release_dossier(
    dossier_path: str | Path,
    *,
    max_children: int = 1000,
) -> DossierVerificationResult:
    """Verify a release dossier using only its enclosed files."""

    dossier_dir = Path(dossier_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not dossier_dir.is_dir():
        return DossierVerificationResult(
            passed=False,
            status="failed",
            failure_stage="package_structure",
            errors=("dossier directory does not exist",),
        )

    files: dict[str, bytes] = {}
    for entry in sorted(dossier_dir.iterdir(), key=lambda p: p.name):
        if entry.is_file():
            files[entry.name] = entry.read_bytes()

    payloads: dict[str, Any] = {}
    for name, data in files.items():
        if name.endswith(".json"):
            try:
                payloads[name] = _load_json_bytes(data, name)
            except ValueError as exc:
                errors.append(str(exc))

    envelope = payloads.get(DOSSIER_ENVELOPE_FILE)
    if not isinstance(envelope, dict):
        return DossierVerificationResult(
            passed=False,
            status="failed",
            failure_stage="dossier_envelope",
            errors=("dossier envelope missing or malformed",),
        )

    envelope_errors, envelope_metrics = _validate_envelope(envelope)
    errors.extend(envelope_errors)

    leaf_index_payload = payloads.get(DOSSIER_LEAF_INDEX_FILE)
    if not isinstance(leaf_index_payload, list):
        return DossierVerificationResult(
            passed=False,
            status="failed",
            failure_stage="leaf_index",
            errors=("dossier leaf index missing or malformed", *tuple(errors)),
            metrics=envelope_metrics,
        )

    index_errors, index_metrics = _validate_leaf_index(leaf_index_payload, envelope)
    errors.extend(index_errors)

    merkle_errors, merkle_metrics = _validate_merkle_root(envelope)
    errors.extend(merkle_errors)

    checksums_payload = payloads.get(DOSSIER_CHECKSUMS_FILE)
    checksum_errors, checksum_metrics = _validate_checksums(files, checksums_payload)
    errors.extend(checksum_errors)

    rollup_errors, rollup_metrics = _validate_rollup(envelope, leaf_index_payload)
    errors.extend(rollup_errors)

    metrics: dict[str, Any] = {}
    metrics.update(envelope_metrics)
    metrics.update(index_metrics)
    metrics.update(merkle_metrics)
    metrics.update(checksum_metrics)
    metrics.update(rollup_metrics)

    if errors:
        return DossierVerificationResult(
            passed=False,
            status="failed",
            failure_stage="static_dossier_validation",
            dossier_id=envelope.get("dossier_id"),
            root_hash=envelope.get("root_hash"),
            rollup_status=envelope.get("rollup_status"),
            child_count=len(leaf_index_payload),
            errors=tuple(errors),
            warnings=tuple(warnings),
            metrics=metrics,
        )

    child_paths = _resolve_child_package_paths(leaf_index_payload, dossier_dir)
    if len(child_paths) > max_children:
        errors.append(f"dossier exceeds maximum child count {max_children}")
        return DossierVerificationResult(
            passed=False,
            status="failed",
            failure_stage="child_limits",
            dossier_id=envelope.get("dossier_id"),
            root_hash=envelope.get("root_hash"),
            rollup_status=envelope.get("rollup_status"),
            child_count=len(leaf_index_payload),
            errors=tuple(errors),
            metrics=metrics,
        )

    child_verifications: list[DossierChildVerification] = []
    passed_children = 0
    failed_children = 0
    for leaf, path in zip(leaf_index_payload, child_paths):
        if not isinstance(leaf, dict):
            errors.append(f"leaf entry is not an object: {leaf!r}")
            continue
        result = _verify_child(leaf, path)
        child_verifications.append(result)
        if result.passed:
            passed_children += 1
        else:
            failed_children += 1
            errors.append(f"child package failed: {result.leaf_id} ({result.status})")

    metrics["verified_child_count"] = passed_children
    metrics["failed_child_count"] = failed_children

    if failed_children > 0:
        return DossierVerificationResult(
            passed=False,
            status="failed",
            failure_stage="child_verification",
            dossier_id=envelope.get("dossier_id"),
            root_hash=envelope.get("root_hash"),
            rollup_status=envelope.get("rollup_status"),
            child_count=len(child_verifications),
            passed_child_count=passed_children,
            failed_child_count=failed_children,
            child_verifications=tuple(child_verifications),
            errors=tuple(errors),
            warnings=tuple(warnings),
            metrics=metrics,
        )

    return DossierVerificationResult(
        passed=True,
        status="verified",
        dossier_id=envelope.get("dossier_id"),
        root_hash=envelope.get("root_hash"),
        rollup_status=envelope.get("rollup_status"),
        child_count=len(child_verifications),
        passed_child_count=passed_children,
        failed_child_count=failed_children,
        child_verifications=tuple(child_verifications),
        warnings=(
            "Dossier verification validates the merkle root, dossier checksum integrity, and child-package offline verification; "
            "it does not re-run CAD generation or external checks.",
        ),
        metrics=metrics,
    )


__all__ = [
    "DOSSIER_VERIFIER_VERSION",
    "DossierChildVerification",
    "DossierVerificationResult",
    "verify_release_dossier",
]