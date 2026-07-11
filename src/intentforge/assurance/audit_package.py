"""Portable directory-based audit packages with deterministic logical identity."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path, PurePosixPath
from typing import Any

from intentforge.assurance.renderer import render_assurance_markdown
from intentforge.assurance.schema import AssuranceCase, canonical_digest, safe_relative_path
from intentforge.assurance.validator import validate_assurance_case
from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.evidence_registry import load_evidence_definitions

REQUIRED_FILES = {
    "assurance_case.json", "assurance_case.md", "intent.json", "capability_snapshot.json",
    "evidence_snapshot.json", "validation_summary.json", "reasoning_summary.json", "artifact_manifest.json",
}


def _tool_version() -> str:
    try:
        return version("intentforge")
    except PackageNotFoundError:
        return "source-checkout"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_case(case: AssuranceCase | dict | str | Path) -> AssuranceCase:
    if isinstance(case, AssuranceCase): return case
    if isinstance(case, dict): return AssuranceCase.model_validate(case)
    return AssuranceCase.model_validate_json(Path(case).read_text(encoding="utf-8"))


def _logical_package_id(case: AssuranceCase, inventory: dict[str, str]) -> str:
    return canonical_digest("audit_package", {"assurance_case_id": case.assurance_case_id, "files": inventory})


def compute_audit_package_id(case: AssuranceCase | dict, inventory: dict[str, str]) -> str:
    """Return the deterministic logical package identity for an inventory."""
    return _logical_package_id(_read_case(case), dict(sorted(inventory.items())))


def build_audit_package(case: AssuranceCase | dict | str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Write a safe metadata-focused audit package directory."""

    record = _read_case(case)
    validation = validate_assurance_case(record)
    if not validation.passed:
        raise ValueError("cannot package invalid assurance case: " + "; ".join(validation.errors))
    capabilities = {item.capability_id: item.model_dump(mode="json") for item in load_capability_manifest().capabilities}
    evidence = {item.evidence_id: item.model_dump(mode="json") for item in load_evidence_definitions()}
    payloads: dict[str, bytes] = {
        "assurance_case.json": record.to_json().encode("utf-8"),
        "assurance_case.md": render_assurance_markdown(record).encode("utf-8"),
        "intent.json": _json_bytes(record.structured_intent or record.input_request),
        "capability_snapshot.json": _json_bytes({key: capabilities[key] for key in record.capability_references}),
        "evidence_snapshot.json": _json_bytes({key: evidence[key] for key in record.evidence_references}),
        "validation_summary.json": _json_bytes([item.model_dump(mode="json") for item in record.validation_observations]),
        "reasoning_summary.json": _json_bytes(record.reasoning_summary or {"available": False}),
        "artifact_manifest.json": _json_bytes([item.model_dump(mode="json") for item in record.artifact_records]),
    }
    inventory = {name: _sha256(data) for name, data in sorted(payloads.items())}
    package_id = _logical_package_id(record, inventory)
    manifest = {
        "schema_version": "1.0", "package_id": package_id, "assurance_case_id": record.assurance_case_id,
        "tool_version": _tool_version(), "cad_family": record.cad_family, "operation": record.operation,
        "assurance_profile": record.profile, "validation_status": record.overall_assurance_status,
        "file_inventory": inventory, "limitations": [item.limitation_id for item in record.limitations],
        "review_requirements": record.review_requirements,
    }
    payloads["manifest.json"] = _json_bytes(manifest)
    checksums = {name: _sha256(data) for name, data in sorted(payloads.items())}
    payloads["checksums.json"] = _json_bytes(checksums)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        safe_relative_path(name)
        (root / name).write_bytes(data)
    return {"package_id": package_id, "package_path": str(root), "assurance_case_id": record.assurance_case_id,
            "file_count": len(payloads), "validation": validate_audit_package(root)}


def validate_audit_package(package_path: str | Path) -> dict[str, Any]:
    root = Path(package_path)
    errors: list[str] = []
    if not root.is_dir(): return {"passed": False, "errors": ["audit package directory does not exist"]}
    names = {item.name for item in root.iterdir() if item.is_file()}
    missing = sorted(REQUIRED_FILES.union({"manifest.json", "checksums.json"}) - names)
    if missing: errors.append("missing required files: " + ", ".join(missing))
    forbidden = [item.name for item in root.rglob("*") if any(part in {".git", ".claude", "CLAUDE.md"} for part in item.relative_to(root).parts)]
    if forbidden: errors.append("forbidden package paths: " + ", ".join(sorted(forbidden)))
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        checksums = json.loads((root / "checksums.json").read_text(encoding="utf-8"))
        case = AssuranceCase.model_validate_json((root / "assurance_case.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"passed": False, "errors": errors + [f"invalid package data: {exc}"]}
    hash_mismatches = []
    for name, expected in checksums.items():
        try: safe_relative_path(name)
        except ValueError: errors.append(f"unsafe inventory path: {name}"); continue
        path = root / name
        if not path.is_file() or _sha256(path.read_bytes()) != expected: hash_mismatches.append(name)
    if hash_mismatches: errors.append("checksum mismatch: " + ", ".join(sorted(hash_mismatches)))
    logical_inventory = manifest.get("file_inventory", {})
    for name, expected in logical_inventory.items():
        path = root / name
        if not path.is_file() or _sha256(path.read_bytes()) != expected: errors.append(f"logical inventory mismatch: {name}")
    expected_package_id = _logical_package_id(case, logical_inventory)
    if manifest.get("package_id") != expected_package_id: errors.append("package content ID mismatch")
    if manifest.get("assurance_case_id") != case.assurance_case_id: errors.append("assurance case ID mismatch")
    case_validation = validate_assurance_case(case)
    if not case_validation.passed: errors.extend(case_validation.errors)
    return {"passed": not errors, "errors": errors, "package_id": manifest.get("package_id"),
            "assurance_case_id": case.assurance_case_id, "file_count": len(names),
            "hash_mismatch_count": len(hash_mismatches)}


def inspect_audit_package(package_path: str | Path) -> dict[str, Any]:
    root = Path(package_path)
    validation = validate_audit_package(root)
    manifest = {}
    if (root / "manifest.json").is_file():
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return {"validation": validation, "manifest": manifest, "files": sorted(item.name for item in root.iterdir() if item.is_file()) if root.is_dir() else []}
