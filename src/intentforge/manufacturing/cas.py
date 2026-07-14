"""Content-addressed manufacturing routing-slip envelopes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from intentforge.assurance.schema import safe_relative_path
from intentforge.dossier.merkle import build_merkle_tree, rebuild_merkle_root
from intentforge.manufacturing.schema import ManufacturingOrder, manufacturing_content_address
from intentforge.manufacturing.orders import build_component_manufacturing_order
from intentforge.review.portability import canonical_json_bytes, portability_violations


MANUFACTURING_CAS_SCHEMA_VERSION = "1.0"


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def build_component_manufacturing_envelope(
    *,
    manifest: Any,
    order: ManufacturingOrder,
    step_path: str | Path,
    stl_path: str | Path,
    validation_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Bind one routing slip directly into a component artifact Merkle tree."""

    source_paths = {
        "manufacturing_order.json": Path(output_path).parent / "manufacturing_order.json",
        Path(step_path).name: Path(step_path),
        Path(stl_path).name: Path(stl_path),
        Path(validation_path).name: Path(validation_path),
    }
    leaves = [
        {
            "logical_path": safe_relative_path(name),
            "role": "manufacturing_order" if name == "manufacturing_order.json" else
                    "validation" if name == Path(validation_path).name else "cad_artifact",
            "content_address": _sha256_bytes(path.read_bytes()),
        }
        for name, path in sorted(source_paths.items())
    ]
    manifest_payload = manifest.model_dump(mode="json")
    manifest_leaf = {
        "logical_path": "topology_manifest_snapshot",
        "role": "topology_manifest",
        "content_address": manufacturing_content_address(manifest_payload),
    }
    leaves.append(manifest_leaf)
    leaves.sort(key=lambda item: item["logical_path"])
    merkle = build_merkle_tree([item["content_address"] for item in leaves])
    payload = {
        "schema_version": MANUFACTURING_CAS_SCHEMA_VERSION,
        "hash_algorithm": "sha256",
        "topology_family": manifest.topology_family,
        "topology_manifest_content_address": manifest.content_address,
        "manufacturing_order_content_address": order.content_address,
        "manufacturing_order_leaf_address": next(
            item["content_address"] for item in leaves if item["role"] == "manufacturing_order"
        ),
        "leaves": leaves,
        "merkle_root": merkle.root_hash,
    }
    envelope = {**payload, "content_address": manufacturing_content_address(payload)}
    violations = portability_violations(envelope, location="manufacturing_cas_envelope.json")
    if violations:
        raise ValueError("non-portable manufacturing CAS envelope: " + "; ".join(violations))
    destination = Path(output_path)
    destination.write_bytes(canonical_json_bytes(envelope))
    return envelope


def validate_component_manufacturing_envelope(
    envelope_path: str | Path,
    *,
    manifest: Any | None = None,
) -> dict[str, Any]:
    """Validate routing-slip hash, direct leaf, Merkle root, and CAS identity."""

    path = Path(envelope_path)
    errors: list[str] = []
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"passed": False, "errors": [f"invalid manufacturing CAS envelope: {exc}"]}
    addresses: list[str] = []
    order_address = None
    roles: list[str] = []
    for leaf in envelope.get("leaves", []):
        logical_path = str(leaf.get("logical_path", ""))
        if logical_path == "topology_manifest_snapshot":
            if manifest is None:
                errors.append("topology manifest required to validate manufacturing envelope")
                continue
            actual = manufacturing_content_address(manifest.model_dump(mode="json"))
        else:
            try:
                safe = safe_relative_path(logical_path)
                actual = _sha256_bytes((path.parent / safe).read_bytes())
            except (OSError, ValueError) as exc:
                errors.append(f"invalid manufacturing leaf {logical_path}: {exc}")
                continue
        if actual != leaf.get("content_address"):
            errors.append(f"manufacturing leaf hash mismatch: {logical_path}")
        if leaf.get("role") == "manufacturing_order":
            order_address = actual
            try:
                order = ManufacturingOrder.model_validate_json((path.parent / logical_path).read_text(encoding="utf-8"))
                if envelope.get("manufacturing_order_content_address") != order.content_address:
                    errors.append("manufacturing order content address mismatch")
            except (OSError, ValueError) as exc:
                errors.append(f"invalid manufacturing order: {exc}")
        roles.append(str(leaf.get("role", "")))
        addresses.append(actual)
    expected_role_counts = {
        "manufacturing_order": 1,
        "validation": 1,
        "cad_artifact": 2,
        "topology_manifest": 1,
    }
    actual_role_counts = {role: roles.count(role) for role in set(roles)}
    if actual_role_counts != expected_role_counts:
        errors.append("manufacturing CAS leaf roles mismatch")
    if manifest is not None:
        try:
            expected_order = build_component_manufacturing_order(manifest)
            if envelope.get("manufacturing_order_content_address") != expected_order.content_address:
                errors.append("manufacturing order differs from topology manifest requirements")
        except ValueError as exc:
            errors.append(f"could not derive expected manufacturing order: {exc}")
    try:
        root = rebuild_merkle_root(addresses)
    except ValueError as exc:
        errors.append(f"invalid manufacturing Merkle leaves: {exc}")
        root = None
    if envelope.get("merkle_root") != root:
        errors.append("manufacturing Merkle root mismatch")
    if envelope.get("manufacturing_order_leaf_address") != order_address:
        errors.append("manufacturing order leaf address mismatch")
    payload = dict(envelope)
    supplied = payload.pop("content_address", None)
    expected = manufacturing_content_address(payload)
    if supplied != expected:
        errors.append("manufacturing CAS content address mismatch")
    if manifest is not None and envelope.get("topology_manifest_content_address") != manifest.content_address:
        errors.append("manufacturing topology manifest address mismatch")
    return {
        "passed": not errors,
        "errors": errors,
        "content_address": supplied,
        "merkle_root": root,
        "leaf_count": len(addresses),
    }
