from importlib import resources
from pathlib import Path


def test_pyproject_packages_review_policy_yaml() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert '"intentforge.review.data" = ["*.yaml"]' in pyproject


def test_review_policy_resource_loads_without_repository_path() -> None:
    resource = resources.files("intentforge.review.data").joinpath("review_policies.yaml")
    assert resource.is_file()
    assert resource.read_text(encoding="utf-8").startswith('manifest_version: "1.0"')
