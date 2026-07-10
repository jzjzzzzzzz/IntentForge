import pytest
from pydantic import ValidationError

from intentforge.knowledge.capability_schema import (
    CapabilityDefinition,
    EvidenceReference,
)


def _evidence(reference: str = "intentforge.parser.requirement_parser") -> EvidenceReference:
    return EvidenceReference(
        evidence_type="parser",
        reference=reference,
        description="parser evidence",
        family="wall_mounted_bracket",
        stage="parsing",
    )


def test_valid_capability_definition() -> None:
    capability = CapabilityDefinition(
        capability_id="wall_test_capability",
        title="Test capability",
        description="A stable test capability.",
        family="wall_mounted_bracket",
        status="supported",
        stages=["parsing"],
        implementation_evidence=[_evidence()],
        verification_evidence=[
            EvidenceReference(
                evidence_type="benchmark_case",
                reference="clean_001",
                description="benchmark evidence",
            )
        ],
        version="1.0",
    )

    assert capability.capability_id == "wall_test_capability"


def test_unknown_status_rejected() -> None:
    with pytest.raises(ValidationError):
        CapabilityDefinition(
            capability_id="wall_bad_status",
            title="Bad",
            description="Bad status.",
            family="wall_mounted_bracket",
            status="mostly_supported",
            stages=["parsing"],
            implementation_evidence=[_evidence()],
            verification_evidence=[],
        )


def test_unknown_stage_rejected() -> None:
    with pytest.raises(ValidationError):
        CapabilityDefinition(
            capability_id="wall_bad_stage",
            title="Bad",
            description="Bad stage.",
            family="wall_mounted_bracket",
            status="supported",
            stages=["magic"],
            implementation_evidence=[_evidence()],
            verification_evidence=[],
        )


def test_path_traversal_evidence_rejected() -> None:
    with pytest.raises(ValidationError):
        _evidence("../secrets.txt")


def test_partial_capability_requires_limitations() -> None:
    with pytest.raises(ValidationError):
        CapabilityDefinition(
            capability_id="wall_partial_without_limits",
            title="Partial",
            description="Missing limitations.",
            family="wall_mounted_bracket",
            status="partially_supported",
            stages=["feature_recognition"],
            implementation_evidence=[_evidence()],
            verification_evidence=[],
        )


def test_unsupported_capability_requires_rejection_behavior() -> None:
    with pytest.raises(ValidationError):
        CapabilityDefinition(
            capability_id="wall_unsupported_without_boundary",
            title="Unsupported",
            description="Missing boundary behavior.",
            family="wall_mounted_bracket",
            status="unsupported",
            stages=["rejection"],
            implementation_evidence=[_evidence()],
            verification_evidence=[],
        )
