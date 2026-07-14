"""Pure builders and canonical writer for manufacturing orders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from intentforge.manufacturing.schema import ManufacturingOrder, ManufacturingOrderItem
from intentforge.review.portability import canonical_json_bytes


def build_component_manufacturing_order(manifest: Any) -> ManufacturingOrder:
    return ManufacturingOrder(
        order_scope="component",
        subject_family=manifest.topology_family,
        subject_manifest_version=manifest.manifest_version,
        subject_manifest_content_address=manifest.content_address,
        subject_requirements=manifest.manufacturing_requirements,
        items=[
            ManufacturingOrderItem(
                item_id=manifest.topology_family,
                topology_family=manifest.topology_family,
                quantity=1,
                manifest_version=manifest.manifest_version,
                manifest_content_address=manifest.content_address,
                requirements=manifest.manufacturing_requirements,
            )
        ],
        limitations=list(manifest.limitations),
    )


def build_assembly_manufacturing_order(
    manifest: Any,
    component_manifests: dict[str, Any],
    quantities: dict[str, int],
) -> ManufacturingOrder:
    items = []
    for component in manifest.components:
        topology = component_manifests[component.component_id]
        items.append(
            ManufacturingOrderItem(
                item_id=component.component_id,
                topology_family=topology.topology_family,
                quantity=quantities[component.component_id],
                manifest_version=topology.manifest_version,
                manifest_content_address=topology.content_address,
                requirements=topology.manufacturing_requirements,
            )
        )
    return ManufacturingOrder(
        order_scope="assembly",
        subject_family=manifest.assembly_family,
        subject_manifest_version=manifest.manifest_version,
        subject_manifest_content_address=manifest.content_address,
        subject_requirements=manifest.manufacturing_requirements,
        items=items,
        limitations=list(manifest.limitations),
    )


def write_manufacturing_order(order: ManufacturingOrder, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(canonical_json_bytes(order.model_dump(mode="json")))
    return destination
