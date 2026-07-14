"""Validated manufacturing requirements and model-based routing slips."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ManufacturingOrderScope = Literal["component", "assembly"]
ToleranceType = Literal[
    "flatness",
    "concentricity",
    "cylindricity",
    "perpendicularity",
    "parallelism",
    "position",
    "profile",
    "runout",
]


def manufacturing_content_address(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class MaterialSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    material_grade: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    hardness: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    surface_treatment: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class SurfaceRoughnessRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    controlled_feature: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    requirement: str = Field(pattern=r"^Ra_[0-9]+(?:\.[0-9]+)?$")


class GeometricTolerance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    controlled_feature: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    tolerance_type: ToleranceType
    maximum_allowable_deviation_mm: float = Field(gt=0)
    reference_feature: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def validate_reference_semantics(self) -> "GeometricTolerance":
        if self.tolerance_type == "concentricity" and self.reference_feature is None:
            raise ValueError("concentricity requires a reference_feature")
        return self


class ManufacturingRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    material_specification: MaterialSpecification
    surface_roughness: list[SurfaceRoughnessRequirement] = Field(default_factory=list)
    geometric_tolerances: list[GeometricTolerance] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_controls(self) -> "ManufacturingRequirements":
        roughness_keys = [item.controlled_feature for item in self.surface_roughness]
        tolerance_keys = [
            (item.controlled_feature, item.tolerance_type, item.reference_feature)
            for item in self.geometric_tolerances
        ]
        if len(roughness_keys) != len(set(roughness_keys)):
            raise ValueError("surface roughness controlled features must be unique")
        if len(tolerance_keys) != len(set(tolerance_keys)):
            raise ValueError("geometric tolerance controls must be unique")
        return self


class ManufacturingOrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    topology_family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    quantity: int = Field(ge=1)
    manifest_version: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    manifest_content_address: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    requirements: ManufacturingRequirements | None = None


class ManufacturingOrder(BaseModel):
    """Canonical digital routing slip; runtime paths and timestamps are excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    order_scope: ManufacturingOrderScope
    subject_family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    subject_manifest_version: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    subject_manifest_content_address: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    subject_requirements: ManufacturingRequirements | None = None
    items: list[ManufacturingOrderItem] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    content_address: str = ""

    @model_validator(mode="after")
    def validate_and_address(self) -> "ManufacturingOrder":
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("manufacturing order item IDs must be unique")
        payload = self.model_dump(mode="json")
        payload.pop("content_address", None)
        expected = manufacturing_content_address(payload)
        if self.content_address and self.content_address != expected:
            raise ValueError("manufacturing order content address mismatch")
        if not self.content_address:
            object.__setattr__(self, "content_address", expected)
        return self
