"""Schemas for topology and shape inspection reports."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TopologyMetric(BaseModel):
    """One topology or geometry measurement from a CAD shape."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    name: str = Field(..., min_length=1)
    value: Any = None
    unit: str | None = None
    available: bool = True
    description: str = ""


class TopologyWarning(BaseModel):
    """Non-fatal issue encountered while inspecting a shape."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    metric: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    severity: Literal["warning"] = "warning"


class ShapeInspectionReport(BaseModel):
    """Structured topology-informed inspection report for a CadQuery/OpenCascade shape."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    family: str | None = None
    shape_type: str | None = None
    bounding_box_dimensions_mm: dict[str, float] | None = None
    bounding_box_min_mm: dict[str, float] | None = None
    bounding_box_max_mm: dict[str, float] | None = None
    volume_mm3: float | None = None
    surface_area_mm2: float | None = None
    solid_count: int | None = None
    face_count: int | None = None
    edge_count: int | None = None
    vertex_count: int | None = None
    is_valid: bool | None = None
    center_of_mass_mm: dict[str, float] | None = None
    metrics: list[TopologyMetric] = Field(default_factory=list)
    warnings: list[TopologyWarning] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureRecognitionReport(BaseModel):
    """Structured topology-informed feature recognition report."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    object_type: str = Field(..., min_length=1)
    recognized_features: dict[str, dict[str, Any]] = Field(default_factory=dict)
    topology_checks: dict[str, Any] = Field(default_factory=dict)
    passed: bool = True
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
