from importlib import resources
from pathlib import Path

import yaml

from intentforge.review import load_review_policies, validate_review_policy_manifest


def test_default_manifest_has_five_narrow_policies() -> None:
    policies = load_review_policies()
    assert len(policies) == 5
    assert sum(len(item.checks) for item in policies) == 54
    assert {item.subject_type for item in policies} == {"design_result", "edit_result", "safe_rejection"}


def test_packaged_manifest_resource_exists() -> None:
    resource = resources.files("intentforge.review.data").joinpath("review_policies.yaml")
    assert resource.is_file()
    assert "intentforge_standard_design_review_v1" in resource.read_text(encoding="utf-8")


def test_malformed_yaml_fails_validation(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("policies: [", encoding="utf-8")
    result = validate_review_policy_manifest(path=path)
    assert not result.passed
    assert "invalid review policy manifest" in result.errors[0]


def test_duplicate_policy_ids_fail_validation(tmp_path: Path) -> None:
    resource = resources.files("intentforge.review.data").joinpath("review_policies.yaml")
    data = yaml.safe_load(resource.read_text(encoding="utf-8"))
    data["policies"].append(data["policies"][0])
    path = tmp_path / "duplicate.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = validate_review_policy_manifest(path=path)
    assert not result.passed
    assert result.metrics["duplicate_policy_id_count"] == 1
