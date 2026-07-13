"""Validated declarative schema for registered CAD topology families."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ParameterType = Literal["float", "integer", "boolean", "string"]
TopologyStatus = Literal["active", "deprecated"]


class ControlledParameter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    parameter_type: ParameterType
    default: float | int | bool | str
    unit: str | None = None
    safe_bounds: tuple[float, float] | None = None
    allowed_values: tuple[str, ...] | None = None
    description: str = Field(min_length=1)
    required: bool = True

    @model_validator(mode="after")
    def validate_default_and_bounds(self) -> "ControlledParameter":
        expected = {
            "float": (int, float),
            "integer": (int,),
            "boolean": (bool,),
            "string": (str,),
        }[self.parameter_type]
        if isinstance(self.default, bool) and self.parameter_type != "boolean":
            raise ValueError(f"{self.name} default has the wrong type")
        if not isinstance(self.default, expected):
            raise ValueError(f"{self.name} default has the wrong type")
        if self.safe_bounds is not None:
            low, high = self.safe_bounds
            if low >= high:
                raise ValueError(f"{self.name} safe_bounds must be increasing")
            if self.parameter_type not in {"float", "integer"}:
                raise ValueError(f"{self.name} non-numeric parameter cannot define safe_bounds")
            if not low <= float(self.default) <= high:
                raise ValueError(f"{self.name} default is outside safe_bounds")
        if self.allowed_values is not None:
            if self.parameter_type != "string":
                raise ValueError(f"{self.name} allowed_values require a string parameter")
            if not self.allowed_values or len(self.allowed_values) != len(set(self.allowed_values)):
                raise ValueError(f"{self.name} allowed_values must be non-empty and unique")
            if self.default not in self.allowed_values:
                raise ValueError(f"{self.name} default is outside allowed_values")
        return self


class SupportedFeature(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    operation: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    description: str = Field(min_length=1)
    default_enabled: bool = True
    parameter_names: list[str] = Field(default_factory=list)


class RuleVariableMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    expression: str = Field(min_length=1)
    remediation_parameter: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    rule_ids: list[str] = Field(default_factory=list)


class CapabilityEvidenceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_catalog_ids: list[str] = Field(default_factory=list)
    applicable_evidence_ids: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    rule_variable_mapping: list[RuleVariableMapping] = Field(default_factory=list)
    scope_note: str = Field(min_length=1)


class TopologyManifest(BaseModel):
    """One immutable topology profile selected through closed adapter registries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    topology_family: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    manifest_version: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    status: TopologyStatus = "active"
    aliases: list[str] = Field(min_length=1)
    parser_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    geometry_factory_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    validator_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    controlled_parameters: list[ControlledParameter] = Field(min_length=1)
    supported_features: list[SupportedFeature] = Field(min_length=1)
    capability_evidence_binding: CapabilityEvidenceBinding
    limitations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_manifest(self) -> "TopologyManifest":
        parameter_names = [item.name for item in self.controlled_parameters]
        feature_ids = [item.feature_id for item in self.supported_features]
        if len(parameter_names) != len(set(parameter_names)):
            raise ValueError("controlled parameter names must be unique")
        if len(feature_ids) != len(set(feature_ids)):
            raise ValueError("supported feature IDs must be unique")
        known_parameters = set(parameter_names)
        for feature in self.supported_features:
            unknown = sorted(set(feature.parameter_names) - known_parameters)
            if unknown:
                raise ValueError(f"feature {feature.feature_id} references unknown parameters: {', '.join(unknown)}")
        for mapping in self.capability_evidence_binding.rule_variable_mapping:
            if mapping.remediation_parameter not in known_parameters:
                raise ValueError(
                    f"metric {mapping.metric} remediates unknown parameter {mapping.remediation_parameter}"
                )
        if len(self.aliases) != len(set(alias.lower() for alias in self.aliases)):
            raise ValueError("topology aliases must be unique")
        return self

    def parameter(self, name: str) -> ControlledParameter:
        for item in self.controlled_parameters:
            if item.name == name:
                return item
        raise KeyError(name)

    def metric_mapping(self, metric: str) -> RuleVariableMapping:
        for item in self.capability_evidence_binding.rule_variable_mapping:
            if item.metric == metric:
                return item
        raise KeyError(metric)
