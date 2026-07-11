from intentforge.assurance import build_assurance_from_prompt, validate_assurance_case


def test_unknown_references_fail_validation() -> None:
    case = build_assurance_from_prompt(profile="static")
    invalid = case.model_copy(update={"capability_references": [*case.capability_references, "missing_capability"]})
    result = validate_assurance_case(invalid)
    assert not result.passed
    assert result.metrics["invalid_capability_reference_count"] == 1


def test_content_id_tampering_detected() -> None:
    case = build_assurance_from_prompt(profile="static")
    invalid = case.model_copy(update={"content_id": "assurance_content_tampered"})
    assert "assurance content ID mismatch" in validate_assurance_case(invalid).errors
