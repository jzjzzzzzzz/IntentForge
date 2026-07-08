"""Constraint graph schemas for preserving design intent."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SupportedFamily = Literal["wall_mounted_bracket"]
ConstraintKind = Literal[
    "dimensional",
    "geometric",
    "manufacturing",
    "dependency",
    "validation",
]
ConstraintSeverity = Literal["info", "warning", "error"]


class Constraint(BaseModel):
    """A named relationship that should remain true across edits."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_:-]*$",
        description="Stable constraint identifier.",
    )
    kind: ConstraintKind = Field(..., description="Constraint category.")
    expression: str = Field(
        ...,
        min_length=1,
        description="Human-readable or machine-readable constraint expression.",
    )
    parameters: list[str] = Field(
        default_factory=list,
        description="Parameter names referenced by this constraint.",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Why this constraint preserves design intent.",
    )
    severity: ConstraintSeverity = Field(default="error")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConstraintGraph(BaseModel):
    """Constraints plus dependency edges between parameters or features."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    family: SupportedFamily = Field(..., description="Supported CAD model family.")
    nodes: list[str] = Field(
        default_factory=list,
        description="Known graph nodes, usually parameter names or feature IDs.",
    )
    dependencies: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Directed dependency map: key depends on listed nodes.",
    )
    constraints: list[Constraint] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self) -> "ConstraintGraph":
        constraint_ids = [constraint.id for constraint in self.constraints]
        duplicates = sorted(
            {constraint_id for constraint_id in constraint_ids if constraint_ids.count(constraint_id) > 1}
        )
        if duplicates:
            joined = ", ".join(duplicates)
            raise ValueError(f"duplicate constraint ids: {joined}")

        if self.nodes:
            node_set = set(self.nodes)
            missing_sources = sorted(set(self.dependencies) - node_set)
            if missing_sources:
                joined = ", ".join(missing_sources)
                raise ValueError(f"dependency sources missing from nodes: {joined}")

            missing_targets = sorted(
                {
                    target
                    for targets in self.dependencies.values()
                    for target in targets
                    if target not in node_set
                }
            )
            if missing_targets:
                joined = ", ".join(missing_targets)
                raise ValueError(f"dependency targets missing from nodes: {joined}")

        return self
