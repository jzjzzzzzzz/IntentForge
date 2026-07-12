from __future__ import annotations

from importlib.metadata import version
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from intentforge.assurance import build_audit_package
from intentforge.assurance.schema import ArtifactRecord, AssuranceCase, safe_relative_path
from intentforge.review import evaluate_assurance_case, get_review_policy
from intentforge.review.portability import (
    canonical_json_bytes,
    make_portable_assurance_case,
    normalize_portable_data,
    portability_violations,
)
from tests.review_test_helpers import review_resources, static_case


def test_linux_macos_and_windows_shapes_have_same_canonical_identity() -> None:
    values = [
        {"path": "/tmp/intentforge/output/model.step", "request_id": "linux", "run_id": "1", "runtime_metadata": {"timezone": "UTC"}},
        {"path": "/private/tmp/intentforge/output/model.step", "request_id": "mac", "run_id": "2", "runtime_metadata": {"timezone": "Asia/Singapore"}},
        {"path": r"C:\Users\tester\AppData\Local\Temp\intentforge\output\model.step", "request_id": "windows", "run_id": "3", "runtime_metadata": {"timezone": "Pacific Standard Time"}},
    ]
    normalized = [normalize_portable_data(item) for item in values]
    assert len({canonical_json_bytes(item) for item in normalized}) == 1
    assert normalized[0]["path"] == "output/model.step"
    assert portability_violations(normalized[0]) == []


def test_runtime_timestamps_and_host_metadata_are_excluded() -> None:
    normalized = normalize_portable_data({
        "timestamp": "2026-07-12T10:00:00+08:00",
        "timezone": "Asia/Singapore",
        "platform": "darwin",
        "runtime_metadata": {"hostname": "private-host", "path": "/tmp/private"},
    })
    assert normalized == {
        "platform": "platform_neutral",
        "runtime_metadata": {},
        "timestamp": "deterministic",
        "timezone": "UTC",
    }
    assert portability_violations(normalized) == []


def test_portable_assurance_copy_preserves_content_identity() -> None:
    source = static_case()
    portable = make_portable_assurance_case(source)
    assert portable.assurance_case_id == source.assurance_case_id
    assert portable.content_id == source.content_id
    assert portable.request_id == "portable_request"
    assert portable.runtime_metadata == {}


def test_safe_relative_path_rejects_windows_and_encoded_traversal() -> None:
    with pytest.raises(ValueError):
        safe_relative_path(r"C:\temp\model.step")
    with pytest.raises(ValueError):
        safe_relative_path("%252e%252e/model.step")
    with pytest.raises(ValidationError):
        ArtifactRecord(
            artifact_id="a", artifact_type="step", logical_name="x.step",
            path=r"C:\temp\x.step", producer_operation="build",
            family="wall_mounted_bracket", metadata_id="m",
        )


def test_runtime_ids_do_not_change_portable_package_hashes(tmp_path: Path) -> None:
    source = static_case()
    variant_data = source.model_dump(mode="json")
    variant_data["request_id"] = "host_specific_request"
    variant_data["run_id"] = "host_specific_run"
    variant_data["runtime_metadata"] = {"hostname": "host-a", "timezone": "local"}
    for artifact in variant_data["artifact_records"]:
        artifact["request_id"] = "host_specific_request"
        artifact["run_id"] = "host_specific_run"
    variant = AssuranceCase.model_validate(variant_data)
    policy = get_review_policy("intentforge_static_review_v1")
    decision = evaluate_assurance_case(policy, source, resources=review_resources())
    first = build_audit_package(source, tmp_path / "first", review_policy=policy, review_decision=decision)
    second = build_audit_package(variant, tmp_path / "second", review_policy=policy, review_decision=decision)
    assert first["package_id"] == second["package_id"]
    for name in json.loads((tmp_path / "first" / "checksums.json").read_text()):
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes()


def test_package_manifest_uses_installed_metadata_version(tmp_path: Path) -> None:
    source = static_case()
    policy = get_review_policy("intentforge_static_review_v1")
    decision = evaluate_assurance_case(policy, source, resources=review_resources())
    build_audit_package(source, tmp_path / "package", review_policy=policy, review_decision=decision)
    manifest = json.loads((tmp_path / "package" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["tool_version"] == version("intentforge")
    assert manifest["portability_profile"] == "intentforge_portable_audit_v1"
    assert manifest["canonical_json"] is True


def test_every_json_payload_uses_canonical_encoding(tmp_path: Path) -> None:
    source = static_case()
    policy = get_review_policy("intentforge_static_review_v1")
    decision = evaluate_assurance_case(policy, source, resources=review_resources())
    build_audit_package(source, tmp_path / "package", review_policy=policy, review_decision=decision)
    for path in (tmp_path / "package").glob("*.json"):
        assert path.read_bytes() == canonical_json_bytes(json.loads(path.read_text(encoding="utf-8")))
