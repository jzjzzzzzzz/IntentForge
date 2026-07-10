import pytest
from pydantic import ValidationError

from intentforge.knowledge.evidence_schema import EvidenceDefinition, make_observation


def _definition(**overrides):
    data = {
        "evidence_id": "ev_test_definition",
        "title": "Test evidence",
        "description": "Test evidence description.",
        "evidence_type": "benchmark_case",
        "role": "verification",
        "reference": "clean_001",
        "family": "wall_mounted_bracket",
        "stages": ["cad_generation"],
        "capability_ids": ["wall_basic_mounting_plate_generation"],
        "verification_method": "static_resolution",
        "expected_result": "benchmark_case_exists",
        "required": True,
        "version": "1.0",
    }
    data.update(overrides)
    return EvidenceDefinition.model_validate(data)


def test_valid_evidence_definition_serializes() -> None:
    definition = _definition()
    dumped = definition.model_dump(mode="json")
    assert dumped["evidence_id"] == "ev_test_definition"
    assert dumped["evidence_type"] == "benchmark_case"


def test_unknown_evidence_type_rejected() -> None:
    with pytest.raises(ValidationError):
        _definition(evidence_type="unknown_type")


def test_absolute_and_traversal_references_rejected() -> None:
    with pytest.raises(ValidationError):
        _definition(reference="/tmp/file")
    with pytest.raises(ValidationError):
        _definition(reference="../secret")


def test_runtime_metadata_excluded_from_content_id() -> None:
    definition = _definition()
    first = make_observation(
        definition,
        status="verified",
        observed_result="ok",
        matches_expectation=True,
        verifier="test",
        runtime_metadata={"timestamp": "first"},
    )
    second = make_observation(
        definition,
        status="verified",
        observed_result="ok",
        matches_expectation=True,
        verifier="test",
        runtime_metadata={"timestamp": "second"},
    )
    assert first.content_id == second.content_id
