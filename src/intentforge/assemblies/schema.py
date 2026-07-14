"""Validated declarative schemas for spatial assembly families."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from intentforge.manufacturing.schema import ManufacturingRequirements

AssemblyStatus = Literal["active", "deprecated"]
ConstraintOperator = Literal["lt", "le", "eq", "ge", "gt"]
ConstraintStatus = Literal["pass", "fail", "not_run"]
RemediationDirection = Literal["increase", "decrease", "either"]
RemediationStatus = Literal["applied", "impossible"]
RemediationActionKind = Literal["child_rule", "assembly_constraint"]


def canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class AssemblyComponentDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    component_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    topology_family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    quantity: int | None = Field(default=None, ge=1)
    quantity_expression: str | None = None
    quantity_bindings: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_quantity_source(self) -> "AssemblyComponentDefinition":
        if (self.quantity is None) == (self.quantity_expression is None):
            raise ValueError("component must define exactly one quantity source")
        if self.quantity_expression is not None and not self.quantity_bindings:
            raise ValueError("quantity expression requires bindings")
        return self


class AssemblyRemediationDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target_variable: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    direction: RemediationDirection
    boundary_margin: float = Field(default=0.0, ge=0.0)
    rationale: str = Field(min_length=1)


class SpatialConstraintDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    constraint_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    left_expression: str = Field(min_length=1)
    operator: ConstraintOperator
    right_expression: str = Field(min_length=1)
    variable_bindings: dict[str, str] = Field(min_length=1)
    blocking: bool = True
    remediation: AssemblyRemediationDefinition | None = None

    @model_validator(mode="after")
    def validate_remediation_target(self) -> "SpatialConstraintDefinition":
        if self.remediation is not None and self.remediation.target_variable not in self.variable_bindings:
            raise ValueError("remediation target_variable must reference a declared variable binding")
        if self.operator in {"lt", "gt"} and self.remediation is not None and self.remediation.boundary_margin <= 0:
            raise ValueError("strict inequalities require a positive remediation boundary_margin")
        return self


class AssemblyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assembly_family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    manifest_version: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    status: AssemblyStatus = "active"
    aliases: list[str] = Field(min_length=1)
    assembly_factory_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    components: list[AssemblyComponentDefinition] = Field(min_length=1)
    spatial_constraints: list[SpatialConstraintDefinition] = Field(min_length=1)
    manufacturing_requirements: ManufacturingRequirements | None = None
    limitations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_identifiers(self) -> "AssemblyManifest":
        component_ids = [item.component_id for item in self.components]
        constraint_ids = [item.constraint_id for item in self.spatial_constraints]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("assembly component IDs must be unique")
        if len(constraint_ids) != len(set(constraint_ids)):
            raise ValueError("spatial constraint IDs must be unique")
        if len(self.aliases) != len(set(item.lower() for item in self.aliases)):
            raise ValueError("assembly aliases must be unique")
        return self

    @property
    def content_address(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))

    def component(self, component_id: str) -> AssemblyComponentDefinition:
        for item in self.components:
            if item.component_id == component_id:
                return item
        raise KeyError(component_id)


class AssemblyChildObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_id: str
    component_id: str
    topology_family: str
    validation_passed: bool
    validation_report: dict[str, Any]


class AssemblyConstraintObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    constraint_id: str
    status: ConstraintStatus
    blocking: bool
    left_value: float | None = None
    operator: ConstraintOperator
    right_value: float | None = None
    description: str


class AssemblyRemediationAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    constraint_id: str
    action_kind: RemediationActionKind = "assembly_constraint"
    status: RemediationStatus
    rule_ids: list[str] = Field(default_factory=list)
    component_id: str | None = None
    parameter_name: str | None = None
    previous_value: float | None = None
    proposed_value: float | None = None
    boundary_margin: float = Field(ge=0.0)
    rationale: str


class AssemblyEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    assembly_family: str
    manifest_version: str
    child_observations: list[AssemblyChildObservation]
    constraint_observations: list[AssemblyConstraintObservation]
    remediation_actions: list[AssemblyRemediationAction] = Field(default_factory=list)
    remediation_applied: bool = False
    nested_validation_passed: bool
    passed: bool
    limitations: list[str] = Field(default_factory=list)
    content_address: str = ""

    @model_validator(mode="after")
    def set_content_address(self) -> "AssemblyEvaluationReport":
        payload = self.model_dump(mode="json")
        payload.pop("content_address", None)
        expected = canonical_sha256(payload)
        if self.content_address and self.content_address != expected:
            raise ValueError("assembly evaluation content address mismatch")
        if not self.content_address:
            object.__setattr__(self, "content_address", expected)
        return self
