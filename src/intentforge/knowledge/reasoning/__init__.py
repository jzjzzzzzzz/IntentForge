"""Deterministic engineering reasoning layer for IntentForge."""

from intentforge.knowledge.reasoning.engine import (
    DEFAULT_REASONING_LIMITATIONS,
    EngineeringReasoningError,
    SUPPORTED_REASONING_FAMILIES,
    build_engineering_reasoning_report,
    write_engineering_reasoning_report,
)
from intentforge.knowledge.reasoning.schema import (
    ALLOWED_CONFLICT_TYPES,
    ALLOWED_INTERACTION_TYPES,
    ALLOWED_PRIORITIES,
    ALLOWED_STEP_TYPES,
    EngineeringReasoningReport,
    EngineeringTradeoff,
    PrioritizedRecommendation,
    REASONING_ENGINE_VERSION,
    ReasoningConflict,
    ReasoningStep,
    RuleInteraction,
)
from intentforge.knowledge.reasoning.templates import (
    render_engineering_reasoning_markdown,
    write_engineering_reasoning_markdown,
)

__all__ = [
    "ALLOWED_CONFLICT_TYPES",
    "ALLOWED_INTERACTION_TYPES",
    "ALLOWED_PRIORITIES",
    "ALLOWED_STEP_TYPES",
    "DEFAULT_REASONING_LIMITATIONS",
    "EngineeringReasoningError",
    "EngineeringReasoningReport",
    "EngineeringTradeoff",
    "PrioritizedRecommendation",
    "REASONING_ENGINE_VERSION",
    "ReasoningConflict",
    "ReasoningStep",
    "RuleInteraction",
    "SUPPORTED_REASONING_FAMILIES",
    "build_engineering_reasoning_report",
    "render_engineering_reasoning_markdown",
    "write_engineering_reasoning_markdown",
    "write_engineering_reasoning_report",
]
