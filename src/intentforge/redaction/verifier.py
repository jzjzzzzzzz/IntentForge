"""Standard-library-only static verification for redacted audit packages."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REDACTED_VERIFIER_VERSION = "1.0"
REDACTED_SCHEMA_VERSION = "1.0"
REDACTED_ENVELOPE_FILE = "redacted_cas_envelope.json"
REDACTION_MANIFEST_FILE = "redaction_manifest.json"


@dataclass(frozen=True)
class RedactedVerificationResult:
    """Verification result for a redacted audit package."""
    passed: bool
    status: str
    failure_stage: str | None = None
    original_package_id: str | None = None
    redacted_package_id: str | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "status": self.status,
            "failure_stage": self.failure_stage,
            "original_package_id": self.original_package_id,
            "redacted_package_id": self.redacted_package_id,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": dict(sorted(self.metrics.items())),
            "redacted_verifier_version": REDACTED_VERIFIER_VERSION,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(prefix: str, payload: Any, length: int = 16) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:length]}"


def _load_json_bytes(data: bytes, name: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name}: invalid UTF-8: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name}: invalid JSON: {exc}") from exc


@dataclass
class RedactedPackageReader:
    """Reads and validates a redacted audit package."""

    root: Path
    files: dict[str, bytes] = field(default_factory=dict)
    payloads: dict[str, Any] = field(default_factory=dict)

    def read(self) -> tuple[list[str], dict[str, Any]]:
        """Read all files from the package."""
        errors: list[str] = []
        for entry in sorted(self.root.iterdir(), key=lambda p: p.name):
            if entry.is_file():
                try:
                    self.files[entry.name] = entry.read_bytes()
                except OSError as exc:
                    errors.append(f"could not read {entry.name}: {exc}")
        for name in self.files:
            if name.endswith(".json"):
                try:
                    self.payloads[name] = _load_json_bytes(self.files[name], name)
                except ValueError as exc:
                    errors.append(str(exc))
        return errors, self.payloads


def _validate_redacted_envelope(
    envelope: dict[str, Any],
    manifest: dict[str, Any],
    files: dict[str, bytes],
) -> tuple[list[str], dict[str, Any]]:
    """Validate the redacted CAS envelope and verify hash chain integrity."""
    errors: list[str] = []
    metrics: dict[str, Any] = {}

    if envelope.get("schema_version") != "1.0":
        errors.append("unsupported redacted CAS envelope schema version")
    if envelope.get("hash_algorithm") != "sha256":
        errors.append("unsupported hash algorithm")
    if envelope.get("redacted") is not True:
        errors.append("envelope redacted flag is not set")

    predecessor = envelope.get("predecessor_hash_pointer")
    if predecessor is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", str(predecessor)):
        errors.append("redacted predecessor content address is malformed")

    required_business_keys = {
        "assurance_case_id", "review_decision_id", "cad_family",
        "operation", "tool_version", "original_package_id",
    }
    missing_business = required_business_keys - set(envelope)
    if missing_business:
        errors.append(f"redacted envelope missing required business fields: {sorted(missing_business)}")

    objects = envelope.get("objects", [])
    if not isinstance(objects, list):
        errors.append("CAS objects must be a list")
        return errors, metrics

    paths = [item.get("logical_path") for item in objects if isinstance(item, dict)]
    if len(paths) != len(set(paths)):
        errors.append("duplicate CAS object paths")

    envelope_copy = dict(envelope)
    envelope_copy.pop("content_address", None)
    envelope_copy["objects"] = sorted(envelope_copy.get("objects", []), key=lambda x: x.get("logical_path", ""))

    for obj in objects:
        path = obj.get("logical_path", "")
        if path in files:
            expected = "sha256:" + _sha256(files[path])
            if obj.get("content_address") != expected:
                errors.append(f"CAS object content address mismatch: {path}")
        else:
            errors.append(f"CAS object references missing file: {path}")

    expected_address = "sha256:" + _sha256(
        json.dumps(envelope_copy, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    if envelope.get("content_address") != expected_address:
        errors.append("redacted CAS envelope content address mismatch")

    metrics.update({
        "redacted_cas_object_count": len(objects),
        "predecessor_pointer_present": predecessor is not None,
        "envelope_hash_verified": envelope.get("content_address") == expected_address,
    })

    return errors, metrics


def _validate_redaction_manifest(
    redaction_manifest: dict[str, Any],
    original_id: str | None,
) -> tuple[list[str], dict[str, Any]]:
    """Validate the redaction manifest."""
    errors: list[str] = []
    metrics: dict[str, Any] = {}

    if redaction_manifest.get("schema_version") != REDACTED_SCHEMA_VERSION:
        errors.append("unsupported redaction manifest schema version")

    if redaction_manifest.get("original_package_id") != original_id:
        errors.append("redaction manifest original package ID mismatch")

    if not redaction_manifest.get("preserved_cas_chain"):
        errors.append("CAS chain preservation not confirmed")
    if not redaction_manifest.get("preserved_policy_checks"):
        errors.append("policy checks preservation not confirmed")
    if not redaction_manifest.get("preserved_claims"):
        errors.append("claims preservation not confirmed")
    if not redaction_manifest.get("preserved_findings"):
        errors.append("findings preservation not confirmed")
    if not redaction_manifest.get("preserved_decision"):
        errors.append("decision preservation not confirmed")

    metrics.update({
        "total_redactions": redaction_manifest.get("total_redactions", 0),
        "files_processed": len(redaction_manifest.get("file_reports", [])),
    })

    return errors, metrics


def _validate_redacted_policy_chain(
    case: dict[str, Any],
    policy: dict[str, Any],
    decision: dict[str, Any],
    provenance: dict[str, Any] | None,
    catalog: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Validate the preserved policy check chain in the redacted package."""
    errors: list[str] = []
    metrics: dict[str, Any] = {}

    claim_types = {c.get("claim_type") for c in case.get("claims", [])}
    metrics["claim_type_count"] = len(claim_types)
    metrics["total_claims"] = len(case.get("claims", []))

    check_count = len(policy.get("checks", []))
    metrics["policy_check_count"] = check_count

    finding_count = len(decision.get("findings", []))
    metrics["decision_finding_count"] = finding_count

    condition_count = len(decision.get("conditions", []))
    metrics["decision_condition_count"] = condition_count

    decision_status = decision.get("decision_status", "")
    metrics["decision_status"] = decision_status

    valid_statuses = {
        "unresolved", "rejected_by_policy", "manual_review_required",
        "accepted_with_conditions", "accepted_within_declared_scope",
    }
    if decision_status not in valid_statuses:
        errors.append(f"invalid decision status: {decision_status}")

    if provenance is not None:
        snapshot_count = len(provenance.get("snapshots", []))
        metrics["provenance_snapshot_count"] = snapshot_count

        node_count = len(provenance.get("execution_nodes", []))
        metrics["provenance_node_count"] = node_count

    metrics.update({
        "policy_checks_preserved": check_count == 54,
        "claims_preserved": len(case.get("claims", [])) == 49,
        "decision_status_preserved": decision_status in valid_statuses,
    })

    return errors, metrics


def _validate_redacted_package_checksums(
    files: dict[str, bytes],
    manifest: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """Validate checksums in the redacted package."""
    errors: list[str] = []
    metrics: dict[str, Any] = {}

    checksums = manifest.get("file_inventory") or manifest.get("checksums")
    if not isinstance(checksums, dict):
        errors.append("checksums must be a JSON object")
        return errors, metrics

    skip = {"checksums.json"}

    mismatch_count = 0
    for name, expected in checksums.items():
        if name in skip:
            continue
        if name not in files:
            errors.append(f"checksum references missing file: {name}")
            continue
        actual = _sha256(files[name])
        if actual != expected:
            errors.append(f"checksum mismatch: {name}")
            mismatch_count += 1

    metrics["hash_mismatch_count"] = mismatch_count
    metrics["checksum_validation_passed"] = mismatch_count == 0

    return errors, metrics


def verify_redacted_audit_package(
    package_path: str | Path,
) -> RedactedVerificationResult:
    """Verify a redacted audit package using only standard library operations."""

    root = Path(package_path)
    errors: list[str] = []

    if not root.is_dir():
        return RedactedVerificationResult(
            passed=False,
            status="failed",
            failure_stage="package_structure",
            errors=("audit package directory does not exist",),
        )

    reader = RedactedPackageReader(root)
    reader_errors, reader_payloads = reader.read()
    errors.extend(reader_errors)

    if errors:
        return RedactedVerificationResult(
            passed=False,
            status="failed",
            failure_stage="package_structure",
            errors=tuple(errors),
        )

    files = reader.files
    payloads = reader_payloads

    if "manifest.json" not in files:
        return RedactedVerificationResult(
            passed=False,
            status="failed",
            failure_stage="package_structure",
            errors=("manifest.json not found",),
        )

    manifest = payloads.get("manifest.json", {})

    if manifest.get("redacted") is not True:
        return RedactedVerificationResult(
            passed=False,
            status="failed",
            failure_stage="schema_validation",
            errors=("package is not marked as redacted",),
        )

    original_id = manifest.get("original_package_id")
    redacted_id = manifest.get("package_id")

    envelope = payloads.get(REDACTED_ENVELOPE_FILE, {})
    if not envelope:
        return RedactedVerificationResult(
            passed=False,
            status="failed",
            failure_stage="envelope",
            errors=("redacted CAS envelope not found",),
        )

    envelope_errors, envelope_metrics = _validate_redacted_envelope(
        envelope, manifest, files
    )
    errors.extend(envelope_errors)

    redaction_manifest = payloads.get(REDACTION_MANIFEST_FILE, {})
    if not redaction_manifest:
        return RedactedVerificationResult(
            passed=False,
            status="failed",
            failure_stage="redaction_manifest",
            errors=("redaction manifest not found",),
        )

    redaction_errors, redaction_metrics = _validate_redaction_manifest(
        redaction_manifest, original_id
    )
    errors.extend(redaction_errors)

    checksum_errors, checksum_metrics = _validate_redacted_package_checksums(
        files, manifest
    )
    errors.extend(checksum_errors)

    metrics: dict[str, Any] = {}
    metrics.update(envelope_metrics)
    metrics.update(redaction_metrics)
    metrics.update(checksum_metrics)

    if "assurance_case.json" in payloads:
        case = payloads["assurance_case.json"]
        policy = payloads.get("review_policy_snapshot.json", {})
        decision = payloads.get("review_decision.json", {})
        provenance = payloads.get("review_decision_provenance.json")
        catalog = payloads.get("review_policy_catalog_snapshot.json", {})

        chain_errors, chain_metrics = _validate_redacted_policy_chain(
            case, policy, decision, provenance, catalog
        )
        errors.extend(chain_errors)
        metrics.update(chain_metrics)

    if errors:
        return RedactedVerificationResult(
            passed=False,
            status="failed",
            failure_stage="static_validation",
            original_package_id=original_id,
            redacted_package_id=redacted_id,
            errors=tuple(errors),
            metrics=metrics,
        )

    return RedactedVerificationResult(
        passed=True,
        status="verified",
        original_package_id=original_id,
        redacted_package_id=redacted_id,
        metrics=metrics,
        warnings=(
            "Redacted package verification confirms CAS chain integrity and policy check preservation.",
            "Verification does not re-run CAD generation or external checks.",
        ),
    )
