from intentforge.review import get_review_policy, validate_review_policy, validate_review_policy_manifest
from intentforge.review.schema import ReviewPolicy


def _changed_policy(policy_id: str, mutate) -> ReviewPolicy:
    data = get_review_policy(policy_id).model_dump(mode="json", serialize_as_any=True)
    mutate(data)
    data["content_id"] = ""
    for check in data["checks"]:
        check["content_id"] = ""
    return ReviewPolicy.model_validate(data)


def test_default_manifest_semantic_validation_passes() -> None:
    result = validate_review_policy_manifest()
    assert result.passed
    assert result.policies_checked == 5
    assert result.checks_checked == 54
    assert not any(result.metrics.values())


def test_unknown_capability_reference_fails_semantic_validation() -> None:
    policy = _changed_policy(
        "intentforge_standard_design_review_v1",
        lambda data: data["checks"][0].update({"related_capability_ids": ["unknown_capability"]}),
    )
    result = validate_review_policy(policy)
    assert not result.passed
    assert result.metrics["unknown_capability_reference_count"] == 1


def test_unknown_evidence_reference_fails_semantic_validation() -> None:
    policy = _changed_policy(
        "intentforge_standard_design_review_v1",
        lambda data: data["checks"][0].update({"related_evidence_ids": ["unknown_evidence"]}),
    )
    assert validate_review_policy(policy).metrics["unknown_evidence_reference_count"] == 1


def test_safe_rejection_policy_cannot_require_artifact_integrity() -> None:
    full_check = get_review_policy("intentforge_full_design_review_v1").checks[0].model_dump(mode="json", serialize_as_any=True)
    artifact_check = next(
        item.model_dump(mode="json", serialize_as_any=True)
        for item in get_review_policy("intentforge_full_design_review_v1").checks
        if item.check_type == "artifact_integrity_required"
    )
    def mutate(data):
        artifact_check["check_id"] = "rejection_artifact_integrity"
        artifact_check["content_id"] = ""
        data["checks"].append(artifact_check)
    policy = _changed_policy("intentforge_safe_rejection_review_v1", mutate)
    result = validate_review_policy(policy)
    assert not result.passed
    assert any("safe-rejection policy" in error for error in result.errors)


def test_static_policy_cannot_require_runtime_validation() -> None:
    runtime_check = next(
        item.model_dump(mode="json", serialize_as_any=True)
        for item in get_review_policy("intentforge_standard_design_review_v1").checks
        if item.check_type == "required_validation_status"
    )
    def mutate(data):
        runtime_check["check_id"] = "static_runtime_validation"
        runtime_check["content_id"] = ""
        data["checks"].append(runtime_check)
    policy = _changed_policy("intentforge_static_review_v1", mutate)
    assert not validate_review_policy(policy).passed
