"""Compatibility exports for the declarative topology registry.

The executable registry lives in :mod:`intentforge.topology` so parser and
schema startup do not eagerly initialize the broad knowledge package facade.
Manifest data remains here as the authoritative knowledge source.
"""

from intentforge.topology import (
    CapabilityEvidenceBinding,
    ControlledParameter,
    RegistryManager,
    RuleVariableMapping,
    SupportedFeature,
    TopologyManifest,
    TopologyRegistryError,
    evaluate_numeric_expression,
    expression_names,
    get_topology_registry,
    registered_family_ids,
    solve_parameter_for_metric,
)

__all__ = [
    "CapabilityEvidenceBinding",
    "ControlledParameter",
    "RegistryManager",
    "RuleVariableMapping",
    "SupportedFeature",
    "TopologyManifest",
    "TopologyRegistryError",
    "evaluate_numeric_expression",
    "expression_names",
    "get_topology_registry",
    "registered_family_ids",
    "solve_parameter_for_metric",
]
