"""Standard-library content-addressed storage and audit-chain verification."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from intentforge.offline_verify import verify_offline_audit_package


CAS_STORAGE_VERSION = "1.0"
_ADDRESS = re.compile(r"^sha256:([0-9a-f]{64})$")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, separators=(",", ": ")) + "\n"


def _content_address(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_cas_address(value: str) -> str:
    if not _ADDRESS.fullmatch(value):
        raise ValueError("CAS address must use sha256:<64 lowercase hex characters>")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _envelope(package_path: Path) -> dict[str, Any]:
    envelope = _read_json(package_path / "cas_envelope.json")
    validate_cas_address(str(envelope.get("content_address", "")))
    predecessor = envelope.get("predecessor_hash_pointer")
    if predecessor is not None:
        validate_cas_address(str(predecessor))
    return envelope


def cas_storage_path(store_root: str | os.PathLike[str], content_address: str) -> Path:
    address = validate_cas_address(content_address)
    digest = address.split(":", 1)[1]
    return Path(store_root) / "sha256" / digest[:2] / digest


def _package_bytes(root: Path) -> dict[str, bytes]:
    return {
        item.name: item.read_bytes()
        for item in sorted(root.iterdir(), key=lambda path: path.name)
        if item.is_file() and not item.is_symlink()
    }


@dataclass(frozen=True)
class CasStoreResult:
    passed: bool
    content_address: str | None
    storage_path: str | None
    reused_existing: bool = False
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "content_address": self.content_address,
            "storage_path": self.storage_path,
            "reused_existing": self.reused_existing,
            "errors": list(self.errors),
            "cas_storage_version": CAS_STORAGE_VERSION,
        }


@dataclass(frozen=True)
class AuditChainVerification:
    passed: bool
    status: str
    head_content_address: str | None = None
    genesis_content_address: str | None = None
    chain_length: int = 0
    chronological_addresses: tuple[str, ...] = ()
    chain_content_address: str | None = None
    verified_package_count: int = 0
    missing_predecessor_count: int = 0
    pointer_mismatch_count: int = 0
    package_validation_failure_count: int = 0
    cycle_count: int = 0
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: dict[str, int | bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "status": self.status,
            "head_content_address": self.head_content_address,
            "genesis_content_address": self.genesis_content_address,
            "chain_length": self.chain_length,
            "chronological_addresses": list(self.chronological_addresses),
            "chain_content_address": self.chain_content_address,
            "verified_package_count": self.verified_package_count,
            "missing_predecessor_count": self.missing_predecessor_count,
            "pointer_mismatch_count": self.pointer_mismatch_count,
            "package_validation_failure_count": self.package_validation_failure_count,
            "cycle_count": self.cycle_count,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": dict(sorted(self.metrics.items())),
            "cas_storage_version": CAS_STORAGE_VERSION,
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def store_audit_package(
    package_path: str | os.PathLike[str],
    store_root: str | os.PathLike[str],
) -> CasStoreResult:
    """Copy a verified package into its immutable content-addressed location."""

    source = Path(package_path)
    verification = verify_offline_audit_package(source)
    if not verification.passed:
        return CasStoreResult(
            passed=False,
            content_address=verification.package_id,
            storage_path=None,
            errors=tuple(verification.errors),
        )
    try:
        envelope = _envelope(source)
        address = str(envelope["content_address"])
        target = cas_storage_path(store_root, address)
        source_files = _package_bytes(source)
        if target.exists():
            if not target.is_dir() or _package_bytes(target) != source_files:
                return CasStoreResult(
                    passed=False,
                    content_address=address,
                    storage_path=str(target),
                    errors=("content-addressed location already contains different bytes",),
                )
            existing = verify_offline_audit_package(target)
            return CasStoreResult(
                passed=existing.passed,
                content_address=address,
                storage_path=str(target),
                reused_existing=True,
                errors=tuple(existing.errors),
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".intentforge-cas-", dir=target.parent))
        try:
            for name, data in source_files.items():
                (temporary / name).write_bytes(data)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
        stored = verify_offline_audit_package(target)
        if not stored.passed:
            return CasStoreResult(
                passed=False,
                content_address=address,
                storage_path=str(target),
                errors=tuple(stored.errors),
            )
        return CasStoreResult(
            passed=True,
            content_address=address,
            storage_path=str(target),
        )
    except (OSError, ValueError) as exc:
        return CasStoreResult(
            passed=False,
            content_address=None,
            storage_path=None,
            errors=(str(exc),),
        )


def infer_cas_store_root(package_path: str | os.PathLike[str]) -> Path | None:
    path = Path(package_path)
    if len(path.parents) >= 3 and path.parent.parent.name == "sha256":
        return path.parent.parent.parent
    return None


def verify_audit_chain(
    head_package_path: str | os.PathLike[str],
    *,
    store_root: str | os.PathLike[str] | None = None,
    maximum_depth: int = 1000,
) -> AuditChainVerification:
    """Verify a head package and every predecessor by full content address."""

    current = Path(head_package_path)
    resolved_store = Path(store_root) if store_root is not None else infer_cas_store_root(current)
    addresses_head_first: list[str] = []
    seen: set[str] = set()
    errors: list[str] = []
    missing = pointer_mismatches = validation_failures = cycles = 0
    expected_address: str | None = None
    for _ in range(maximum_depth):
        if not current.is_dir():
            missing += 1
            errors.append(f"predecessor package is missing: {expected_address or current.name}")
            break
        verification = verify_offline_audit_package(current)
        if not verification.passed:
            validation_failures += 1
            errors.append(
                f"package static verification failed at {expected_address or current.name}: "
                + "; ".join(verification.errors)
            )
            break
        try:
            envelope = _envelope(current)
        except ValueError as exc:
            validation_failures += 1
            errors.append(str(exc))
            break
        address = str(envelope["content_address"])
        if expected_address is not None and address != expected_address:
            pointer_mismatches += 1
            errors.append(f"predecessor pointer mismatch: expected {expected_address}, found {address}")
            break
        if address in seen:
            cycles += 1
            errors.append(f"audit chain cycle detected at {address}")
            break
        seen.add(address)
        addresses_head_first.append(address)
        predecessor = envelope.get("predecessor_hash_pointer")
        if predecessor is None:
            break
        if resolved_store is None:
            missing += 1
            errors.append("CAS store root is required to resolve predecessor packages")
            break
        expected_address = validate_cas_address(str(predecessor))
        current = cas_storage_path(resolved_store, expected_address)
    else:
        errors.append(f"audit chain exceeds maximum depth {maximum_depth}")
    chronological = tuple(reversed(addresses_head_first))
    chain_address = _content_address({"chronological_addresses": list(chronological)}) if chronological else None
    return AuditChainVerification(
        passed=not errors,
        status="verified" if not errors else "failed",
        head_content_address=addresses_head_first[0] if addresses_head_first else None,
        genesis_content_address=chronological[0] if chronological else None,
        chain_length=len(chronological),
        chronological_addresses=chronological,
        chain_content_address=chain_address,
        verified_package_count=len(chronological),
        missing_predecessor_count=missing,
        pointer_mismatch_count=pointer_mismatches,
        package_validation_failure_count=validation_failures,
        cycle_count=cycles,
        errors=tuple(errors),
        warnings=(
            "Chain verification proves internal hash linkage and package integrity; it is not a digital signature or engineering certification.",
        ),
        metrics={
            "chain_length": len(chronological),
            "verified_package_count": len(chronological),
            "missing_predecessor_count": missing,
            "pointer_mismatch_count": pointer_mismatches,
            "package_validation_failure_count": validation_failures,
            "cycle_count": cycles,
        },
    )
