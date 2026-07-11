import json
from pathlib import Path

from intentforge.assurance import build_assurance_from_prompt, build_audit_package, validate_audit_package
from intentforge.assurance.schema import ArtifactRecord


def test_audit_package_creation_and_deterministic_identity(tmp_path: Path) -> None:
    case = build_assurance_from_prompt(profile="static")
    first = build_audit_package(case, tmp_path / "first")
    second = build_audit_package(case, tmp_path / "second")
    assert first["validation"]["passed"]
    assert first["package_id"] == second["package_id"]


def test_modified_package_file_is_detected(tmp_path: Path) -> None:
    case = build_assurance_from_prompt(profile="static")
    build_audit_package(case, tmp_path / "package")
    (tmp_path / "package" / "intent.json").write_text(json.dumps({"modified": True}), encoding="utf-8")
    assert not validate_audit_package(tmp_path / "package")["passed"]


def test_unsafe_artifact_path_rejected() -> None:
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ArtifactRecord(artifact_id="a", artifact_type="step", logical_name="x", path="../x.step",
                       producer_operation="build", family="wall_mounted_bracket", metadata_id="m")
