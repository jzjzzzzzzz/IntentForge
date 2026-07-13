"""Content-addressed assembly audit packages with child Merkle binding."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
from typing import Any

from intentforge.assemblies.schema import AssemblyEvaluationReport, AssemblyManifest, canonical_sha256
from intentforge.assurance.schema import safe_relative_path
from intentforge.dossier.merkle import build_merkle_tree, rebuild_merkle_root
from intentforge.review.portability import canonical_json_bytes, normalize_portable_data, portability_violations
from intentforge.schemas import ParameterTable

ASSEMBLY_AUDIT_SCHEMA_VERSION = "1.0"
REQUIRED_ASSEMBLY_FILES = {
    "assembly_manifest_snapshot.json",
    "assembly_evaluation.json",
    "child_components.json",
    "assembly_cas_envelope.json",
    "assembly.step",
    "manifest.json",
    "checksums.json",
}


def _tool_version() -> str:
    try:
        return version("intentforge")
    except PackageNotFoundError:
        return "source-checkout"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _component_address(record: dict[str, Any]) -> str:
    payload = dict(record)
    payload.pop("content_address", None)
    return canonical_sha256(payload)


def build_assembly_audit_package(
    manifest: AssemblyManifest,
    evaluation: AssemblyEvaluationReport,
    tables: dict[str, ParameterTable],
    placements: list[dict[str, Any]],
    child_artifacts: dict[str, str | Path],
    assembly_step_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Create a parent CAS envelope over the assembly manifest and child artifacts."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    assembly_bytes = Path(assembly_step_path).read_bytes()
    payloads: dict[str, bytes] = {
        "assembly_manifest_snapshot.json": canonical_json_bytes(manifest.model_dump(mode="json")),
        "assembly_evaluation.json": canonical_json_bytes(evaluation.model_dump(mode="json")),
        "assembly.step": assembly_bytes,
    }
    component_records: list[dict[str, Any]] = []
    by_component = {item.component_id: item.topology_family for item in manifest.components}
    from intentforge.topology.registry import get_topology_registry

    for placement in sorted(placements, key=lambda item: item["instance_id"]):
        instance_id = str(placement["instance_id"])
        component_id = str(placement["component_id"])
        logical_path = safe_relative_path(f"children/{instance_id}.step")
        artifact_bytes = Path(child_artifacts[instance_id]).read_bytes()
        payloads[logical_path] = artifact_bytes
        table_payload = tables[component_id].model_dump(mode="json")
        topology_payload = get_topology_registry().get(by_component[component_id]).model_dump(mode="json")
        record = {
            "instance_id": instance_id,
            "component_id": component_id,
            "topology_family": by_component[component_id],
            "topology_manifest": topology_payload,
            "topology_manifest_content_address": canonical_sha256(topology_payload),
            "parameter_table": table_payload,
            "parameter_table_content_address": canonical_sha256(table_payload),
            "placement": normalize_portable_data(placement["location"]),
            "artifact_path": logical_path,
            "artifact_content_address": _sha256_bytes(artifact_bytes),
        }
        record["content_address"] = _component_address(record)
        component_records.append(record)
    payloads["child_components.json"] = canonical_json_bytes(component_records)
    child_tree = build_merkle_tree([item["content_address"] for item in component_records])
    envelope_payload = {
        "schema_version": ASSEMBLY_AUDIT_SCHEMA_VERSION,
        "hash_algorithm": "sha256",
        "assembly_family": manifest.assembly_family,
        "assembly_manifest_content_address": manifest.content_address,
        "assembly_evaluation_content_address": evaluation.content_address,
        "assembly_step_content_address": _sha256_bytes(assembly_bytes),
        "child_component_count": len(component_records),
        "child_component_content_addresses": [item["content_address"] for item in component_records],
        "child_merkle_root": child_tree.root_hash,
    }
    envelope = {**envelope_payload, "content_address": canonical_sha256(envelope_payload)}
    payloads["assembly_cas_envelope.json"] = canonical_json_bytes(envelope)
    for name, data in payloads.items():
        if name.endswith(".json"):
            violations = portability_violations(json.loads(data.decode("utf-8")), location=name)
            if violations:
                raise ValueError("non-portable assembly payload: " + "; ".join(violations))
    inventory = {name: _sha256_bytes(data) for name, data in sorted(payloads.items())}
    package_manifest = {
        "schema_version": ASSEMBLY_AUDIT_SCHEMA_VERSION,
        "package_id": envelope["content_address"],
        "assembly_family": manifest.assembly_family,
        "manifest_version": manifest.manifest_version,
        "tool_version": _tool_version(),
        "child_component_count": len(component_records),
        "child_merkle_root": child_tree.root_hash,
        "file_inventory": inventory,
        "validation_status": "pass" if evaluation.passed else "fail",
    }
    payloads["manifest.json"] = canonical_json_bytes(package_manifest)
    payloads["checksums.json"] = canonical_json_bytes({
        name: _sha256_bytes(data) for name, data in sorted(payloads.items())
    })
    for name, data in payloads.items():
        safe_relative_path(name)
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    validation = validate_assembly_audit_package(root)
    return {
        "package_id": envelope["content_address"],
        "package_path": str(root),
        "child_merkle_root": child_tree.root_hash,
        "child_component_count": len(component_records),
        "validation": validation,
    }


def validate_assembly_audit_package(package_path: str | Path) -> dict[str, Any]:
    """Verify package files, child addresses, Merkle root, and parent CAS identity."""

    root = Path(package_path)
    errors: list[str] = []
    if not root.is_dir():
        return {"passed": False, "errors": ["assembly audit package directory does not exist"]}
    names = {item.relative_to(root).as_posix() for item in root.rglob("*") if item.is_file()}
    missing = sorted(REQUIRED_ASSEMBLY_FILES - names)
    if missing:
        errors.append("missing required files: " + ", ".join(missing))
    try:
        package_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        checksums = json.loads((root / "checksums.json").read_text(encoding="utf-8"))
        assembly_manifest = AssemblyManifest.model_validate_json((root / "assembly_manifest_snapshot.json").read_text(encoding="utf-8"))
        evaluation = AssemblyEvaluationReport.model_validate_json((root / "assembly_evaluation.json").read_text(encoding="utf-8"))
        children = json.loads((root / "child_components.json").read_text(encoding="utf-8"))
        envelope = json.loads((root / "assembly_cas_envelope.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"passed": False, "errors": errors + [f"invalid assembly package data: {exc}"]}
    hash_mismatches: list[str] = []
    for name, expected in sorted(checksums.items()):
        try:
            safe_relative_path(name)
        except ValueError:
            errors.append(f"unsafe checksum path: {name}")
            continue
        path = root / name
        if not path.is_file() or _sha256_bytes(path.read_bytes()) != expected:
            hash_mismatches.append(name)
    if hash_mismatches:
        errors.append("checksum mismatch: " + ", ".join(hash_mismatches))
    component_addresses: list[str] = []
    for child in children if isinstance(children, list) else []:
        try:
            artifact_path = safe_relative_path(str(child["artifact_path"]))
            artifact_address = _sha256_bytes((root / artifact_path).read_bytes())
            if artifact_address != child.get("artifact_content_address"):
                errors.append(f"child artifact hash mismatch: {child.get('instance_id')}")
            if canonical_sha256(child["topology_manifest"]) != child.get("topology_manifest_content_address"):
                errors.append(f"child topology manifest hash mismatch: {child.get('instance_id')}")
            if canonical_sha256(child["parameter_table"]) != child.get("parameter_table_content_address"):
                errors.append(f"child parameter table hash mismatch: {child.get('instance_id')}")
            expected_address = _component_address(child)
            if child.get("content_address") != expected_address:
                errors.append(f"child component address mismatch: {child.get('instance_id')}")
            component_addresses.append(expected_address)
        except (KeyError, OSError, ValueError) as exc:
            errors.append(f"invalid child component record: {exc}")
    try:
        child_merkle_root = rebuild_merkle_root(component_addresses)
    except ValueError as exc:
        errors.append(f"invalid child Merkle leaves: {exc}")
        child_merkle_root = None
    if envelope.get("child_merkle_root") != child_merkle_root:
        errors.append("child Merkle root mismatch")
    if package_manifest.get("child_merkle_root") != child_merkle_root:
        errors.append("package child Merkle root mismatch")
    expected_payload = dict(envelope)
    supplied_address = expected_payload.pop("content_address", None)
    expected_address = canonical_sha256(expected_payload)
    if supplied_address != expected_address or package_manifest.get("package_id") != expected_address:
        errors.append("assembly package content address mismatch")
    if envelope.get("assembly_manifest_content_address") != assembly_manifest.content_address:
        errors.append("assembly manifest content address mismatch")
    if envelope.get("assembly_evaluation_content_address") != evaluation.content_address:
        errors.append("assembly evaluation content address mismatch")
    assembly_path = root / "assembly.step"
    if assembly_path.is_file() and envelope.get("assembly_step_content_address") != _sha256_bytes(assembly_path.read_bytes()):
        errors.append("assembly STEP content address mismatch")
    return {
        "passed": not errors,
        "errors": errors,
        "package_id": package_manifest.get("package_id"),
        "child_merkle_root": child_merkle_root,
        "child_component_count": len(component_addresses),
        "hash_mismatch_count": len(hash_mismatches),
    }
