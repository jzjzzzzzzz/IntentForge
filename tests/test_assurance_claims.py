from intentforge.assurance import build_assurance_from_prompt, validate_assurance_case


def test_static_profile_does_not_claim_runtime_geometry() -> None:
    case = build_assurance_from_prompt(profile="static")
    types = {claim.claim_type for claim in case.claims}
    assert "geometry_generated" not in types
    assert "geometry_valid" not in types


def test_geometry_claim_requires_observation() -> None:
    case = build_assurance_from_prompt(profile="static")
    claim = case.claims[0].model_copy(update={"claim_type": "geometry_valid", "supporting_validation_ids": []})
    invalid = case.model_copy(update={"claims": [claim, *case.claims[1:]]})
    assert not validate_assurance_case(invalid).passed


def test_limitations_require_external_review() -> None:
    case = build_assurance_from_prompt(profile="static")
    assert case.limitations
    assert any(claim.claim_type == "limitation_disclosed" and claim.required_review for claim in case.claims)
