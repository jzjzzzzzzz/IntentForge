from __future__ import annotations

import pytest
from pydantic import ValidationError

from intentforge.review.diff_schema import SemanticDecisionDelta


def test_semantic_delta_identity_is_deterministic() -> None:
    delta = SemanticDecisionDelta(
        category="outcome",
        entity_key="decision_status",
        change_type="modified",
        before={"status": "accepted_with_conditions"},
        after={"status": "accepted_within_declared_scope"},
        changed_fields=["status"],
        compliance_impact="more_permissive",
        security_relevant=True,
        summary_code="decision_acceptance_elevated",
    )
    assert SemanticDecisionDelta.model_validate(delta.model_dump(mode="json")).delta_id == delta.delta_id


def test_semantic_delta_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        SemanticDecisionDelta(
            category="free_text",
            entity_key="invalid",
            change_type="added",
            after={"value": True},
            summary_code="invalid",
        )
