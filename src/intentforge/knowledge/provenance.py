"""Provenance models for engineering knowledge rules."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from intentforge.knowledge.schema import DesignKnowledgeRule


VerificationLevel = Literal["heuristic", "reference", "validated", "deprecated"]


class RuleProvenance(BaseModel):
    """Traceable source information for one engineering knowledge rule."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    rule_id: str
    source: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    verification_level: VerificationLevel = "heuristic"


def provenance_from_rule(rule: DesignKnowledgeRule) -> RuleProvenance:
    """Create a provenance record from a design knowledge rule."""

    verification_level: VerificationLevel = "deprecated" if rule.status == "deprecated" else "heuristic"
    return RuleProvenance(
        rule_id=rule.id,
        source=rule.source_reference,
        description=rule.description,
        confidence=rule.confidence,
        verification_level=verification_level,
    )
