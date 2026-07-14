"""Declarative topology registry and closed runtime adapters."""

from intentforge.topology.factories import build_registered_model
from intentforge.topology.expressions import (
    evaluate_numeric_expression,
    expression_names,
    solve_parameter_for_metric,
)
from intentforge.topology.registry import (
    RegistryManager,
    TopologyRegistryError,
    get_topology_registry,
    registered_family_ids,
)
from intentforge.topology.rejection import (
    SAFE_REJECTION_SCHEMA_VERSION,
    build_safe_rejection_envelope,
)
from intentforge.topology.schema import (
    CapabilityEvidenceBinding,
    ControlledParameter,
    RuleVariableMapping,
    SupportedFeature,
    TopologyManifest,
)
from intentforge.manufacturing.schema import (
    GeometricTolerance,
    ManufacturingRequirements,
    MaterialSpecification,
    SurfaceRoughnessRequirement,
)
from intentforge.topology.validation import validate_registered_geometry, validate_registered_intent

__all__ = [
    "CapabilityEvidenceBinding",
    "ControlledParameter",
    "GeometricTolerance",
    "ManufacturingRequirements",
    "MaterialSpecification",
    "RegistryManager",
    "RuleVariableMapping",
    "SAFE_REJECTION_SCHEMA_VERSION",
    "SupportedFeature",
    "SurfaceRoughnessRequirement",
    "TopologyManifest",
    "TopologyRegistryError",
    "build_registered_model",
    "build_safe_rejection_envelope",
    "evaluate_numeric_expression",
    "expression_names",
    "get_topology_registry",
    "registered_family_ids",
    "solve_parameter_for_metric",
    "validate_registered_geometry",
    "validate_registered_intent",
]
