"""Redacted audit package builder with CAS lineage preservation."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from intentforge.offline_verify import (
    CAS_ENVELOPE_FILE,
    verify_offline_audit_package,
)
from intentforge.redaction.config import (
    REDACTION_SCHEMA_VERSION,
    RedactionConfig,
    default_redaction_config,
)
from intentforge.redaction.engine import prune_document


REDACTED_SCHEMA_VERSION = "1.0"
REDACTED_ENVELOPE_FILE = "redacted_cas_envelope.json"
REDACTION_MANIFEST_FILE = "redaction_manifest.json"
_IGNORED_FOR_CAS_OBJECTS = {"manifest.json", "checksums.json", REDACTED_ENVELOPE_FILE}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def _content_address(data: Any) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _infer_role(filename: str) -> str:
    """Infer the CAS role from filename."""
    role_map = {
        "assurance_case.json": "assurance",
        "assurance_case.md": "report",
        "intent.json": "intent",
        "capability_snapshot.json": "capability_snapshot",
        "evidence_snapshot.json": "evidence_snapshot",
        "validation_summary.json": "validation",
        "reasoning_summary.json": "reasoning",
        "artifact_manifest.json": "artifact_manifest",
        "review_policy_snapshot.json": "policy",
        "review_policy_catalog_snapshot.json": "policy_catalog",
        "review_decision.json": "decision",
        "review_decision.md": "report",
        "review_decision_provenance.json": "provenance",
        REDACTION_MANIFEST_FILE: "redaction_manifest",
    }
    return role_map.get(filename, "payload")


class RedactedPackageBuilder:
    """Builds privacy-preserving redacted audit packages from original packages."""

    def __init__(self, config: RedactionConfig | None = None):
        self.config = config or default_redaction_config()

    def build(
        self,
        source_package: str | Path,
        output_dir: str | Path,
        *,
        predecessor_hash: str | None = None,
    ) -> dict[str, Any]:
        """Build a redacted audit package from the source."""
        source = Path(source_package)
        output = Path(output_dir)

        verification = verify_offline_audit_package(source)
        if not verification.passed:
            return {
                "passed": False,
                "errors": [f"source package verification failed: {e}" for e in verification.errors],
            }

        original_id = verification.package_id

        files = self._read_package_files(source)
        redacted_files = {}
        redaction_reports = []

        for filename, content in files.items():
            if filename.endswith(".json"):
                try:
                    data = json.loads(content.decode("utf-8"))
                    result = prune_document(data, self.config)
                    redacted_json = json.dumps(
                        result.redacted_document,
                        ensure_ascii=True,
                        indent=2,
                        sort_keys=True,
                        separators=(",", ": "),
                    ) + "\n"
                    redacted_files[filename] = redacted_json.encode("utf-8")
                    redaction_reports.append({
                        "file": filename,
                        "replacement_count": result.metrics.get("total_redactions", 0),
                        "by_rule": result.metrics.get("redactions_by_rule", {}),
                        "by_token_type": result.metrics.get("redactions_by_token_type", {}),
                    })
                except (json.JSONDecodeError, TypeError):
                    redacted_files[filename] = content
            else:
                redacted_files[filename] = content

        manifest = self._build_redacted_manifest(redacted_files, original_id, predecessor_hash)
        redaction_manifest = self._build_redaction_manifest(
            redaction_reports, original_id
        )

        checksums = {name: _sha256(data) for name, data in sorted(redacted_files.items())}

        envelope = self._build_redacted_envelope(
            redacted_files, manifest, original_id, predecessor_hash
        )

        manifest["package_id"] = envelope["content_address"]
        manifest["redacted_package_id"] = envelope["content_address"]

        final_files = dict(redacted_files)
        final_files["manifest.json"] = _canonical_json(manifest)
        final_files[REDACTION_MANIFEST_FILE] = _canonical_json(redaction_manifest)
        final_files[REDACTED_ENVELOPE_FILE] = _canonical_json(envelope)

        final_files_for_checksums = {
            k: v for k, v in final_files.items() if k != "manifest.json"
        }
        final_checksums = {
            name: _sha256(data) for name, data in sorted(final_files_for_checksums.items())
        }

        manifest["file_inventory"] = final_checksums
        final_files["manifest.json"] = _canonical_json(manifest)

        temporary = Path(tempfile.mkdtemp(prefix=".intentforge-redacted-"))
        try:
            for name, data in sorted(final_files.items()):
                (temporary / name).write_bytes(data)
            (temporary / "checksums.json").write_bytes(_canonical_json(final_checksums))

            if output.exists():
                shutil.rmtree(output)
            shutil.copytree(temporary, output)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

        redacted_id = envelope["content_address"]

        return {
            "passed": True,
            "original_package_id": original_id,
            "redacted_package_id": redacted_id,
            "package_path": str(output),
            "file_count": len(redacted_files) + 4,
            "redaction_count": sum(r["replacement_count"] for r in redaction_reports),
            "redaction_report": redaction_reports,
        }

    def _read_package_files(self, package: Path) -> dict[str, bytes]:
        """Read all files from the source package."""
        files = {}
        for entry in sorted(package.iterdir(), key=lambda p: p.name):
            if entry.is_file():
                files[entry.name] = entry.read_bytes()
        return files

    def _build_redacted_manifest(
        self,
        redacted_files: dict[str, bytes],
        original_id: str | None,
        predecessor_hash: str | None,
    ) -> dict[str, Any]:
        """Build the redacted manifest."""
        manifest = {}
        if "manifest.json" in redacted_files:
            try:
                manifest = json.loads(redacted_files["manifest.json"].decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        manifest["schema_version"] = "1.3"
        manifest["redacted"] = True
        manifest["original_package_id"] = original_id
        manifest["redaction_config_version"] = REDACTION_SCHEMA_VERSION
        if predecessor_hash:
            manifest["predecessor_hash_pointer"] = predecessor_hash
        return manifest

    def _build_redaction_manifest(
        self,
        redaction_reports: list[dict[str, Any]],
        original_id: str | None,
    ) -> dict[str, Any]:
        """Build the redaction manifest documenting what was redacted."""
        return {
            "schema_version": REDACTED_SCHEMA_VERSION,
            "redaction_config_version": REDACTION_SCHEMA_VERSION,
            "original_package_id": original_id,
            "file_reports": redaction_reports,
            "total_redactions": sum(r["replacement_count"] for r in redaction_reports),
            "preserved_cas_chain": True,
            "preserved_policy_checks": True,
            "preserved_claims": True,
            "preserved_findings": True,
            "preserved_decision": True,
        }

    def _build_redacted_envelope(
        self,
        redacted_files: dict[str, bytes],
        manifest: dict[str, Any],
        original_id: str | None,
        predecessor_hash: str | None,
    ) -> dict[str, Any]:
        """Build the redacted CAS envelope preserving lineage."""
        objects = []
        for name in sorted(redacted_files.keys()):
            if name in _IGNORED_FOR_CAS_OBJECTS or name == REDACTION_MANIFEST_FILE:
                continue
            objects.append({
                "logical_path": name,
                "role": _infer_role(name),
                "content_address": "sha256:" + _sha256(redacted_files[name]),
            })

        cas_envelope = {}
        if CAS_ENVELOPE_FILE in redacted_files:
            try:
                cas_envelope = json.loads(redacted_files[CAS_ENVELOPE_FILE].decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        envelope = {
            "schema_version": "1.0",
            "hash_algorithm": "sha256",
            "assurance_case_id": manifest.get("assurance_case_id"),
            "review_decision_id": manifest.get("review_decision_id"),
            "cad_family": manifest.get("cad_family"),
            "operation": manifest.get("operation"),
            "tool_version": manifest.get("tool_version"),
            "redacted": True,
            "original_package_id": original_id,
            "objects": objects,
        }
        predecessor = predecessor_hash or cas_envelope.get("predecessor_hash_pointer")
        if predecessor is not None:
            envelope["predecessor_hash_pointer"] = predecessor

        content_address = _content_address(envelope)
        envelope["content_address"] = content_address
        return envelope


def export_redacted_package(
    source_package: str | Path,
    output_dir: str | Path,
    *,
    config: RedactionConfig | None = None,
    predecessor_hash: str | None = None,
) -> dict[str, Any]:
    """Export a redacted audit package from a source package."""
    builder = RedactedPackageBuilder(config)
    return builder.build(source_package, output_dir, predecessor_hash=predecessor_hash)
