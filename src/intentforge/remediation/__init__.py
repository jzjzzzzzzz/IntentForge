"""Deterministic auto-remediation for IntentForge Phase 30."""

from intentforge.remediation.algebra import (
    REMEDIATION_ENGINE_VERSION,
    RemediationAlgebraError,
    RemediationAction,
    RemediationDelta,
    RemediationPlan,
    extract_metric_to_parameter_map,
    metric_to_parameter_transform,
    normalize_inequality,
    synthesize_remediation,
)
from intentforge.remediation.engine import (
    REMEDIATION_INTENT_FILE,
    REMEDIATION_INTENT_SCHEMA_VERSION,
    RemediationEngineResult,
    apply_remediation_to_parameters,
    build_metrics,
    synthesize_remediation_intent,
)

# Backwards-compatible alias for callers referencing the version symbol.
RemediationEngineVersion = REMEDIATION_ENGINE_VERSION

__all__ = [
    "REMEDIATION_ENGINE_VERSION",
    "REMEDIATION_INTENT_FILE",
    "REMEDIATION_INTENT_SCHEMA_VERSION",
    "RemediationAlgebraError",
    "RemediationAction",
    "RemediationDelta",
    "RemediationEngineResult",
    "RemediationEngineVersion",
    "RemediationPlan",
    "apply_remediation_to_parameters",
    "build_metrics",
    "extract_metric_to_parameter_map",
    "normalize_inequality",
    "synthesize_remediation",
    "synthesize_remediation_intent",
]