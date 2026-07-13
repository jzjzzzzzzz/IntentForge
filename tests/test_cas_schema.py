from __future__ import annotations

import pytest
from pydantic import ValidationError

from intentforge.review.cas_schema import (
    AuditPackageCasEnvelope,
    CasObjectRecord,
    sha256_content_address,
)


ADDRESS_A = "sha256:" + "a" * 64
ADDRESS_B = "sha256:" + "b" * 64


def test_sha256_content_address_is_full_and_deterministic() -> None:
    first = sha256_content_address({"b": 2, "a": 1})
    second = sha256_content_address({"a": 1, "b": 2})
    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == 71


def test_cas_envelope_sorts_objects_and_computes_identity() -> None:
    envelope = AuditPackageCasEnvelope(
        assurance_case_id="case",
        review_decision_id="decision",
        cad_family="wall_mounted_bracket",
        operation="parse_build",
        tool_version="0.10.2",
        objects=[
            CasObjectRecord(logical_path="z.json", role="decision", content_address=ADDRESS_A),
            CasObjectRecord(logical_path="a.json", role="assurance", content_address=ADDRESS_B),
        ],
    )
    assert [item.logical_path for item in envelope.objects] == ["a.json", "z.json"]
    assert envelope.content_address == sha256_content_address(envelope.deterministic_payload())


def test_invalid_object_or_predecessor_address_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CasObjectRecord(logical_path="a.json", role="assurance", content_address="short")
    with pytest.raises(ValidationError):
        AuditPackageCasEnvelope(
            predecessor_hash_pointer="sha256:not-hex",
            assurance_case_id="case",
            review_decision_id="decision",
            cad_family="wall_mounted_bracket",
            operation="parse_build",
            tool_version="0.10.2",
            objects=[CasObjectRecord(logical_path="a.json", role="assurance", content_address=ADDRESS_A)],
        )


def test_duplicate_cas_object_path_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AuditPackageCasEnvelope(
            assurance_case_id="case",
            review_decision_id="decision",
            cad_family="wall_mounted_bracket",
            operation="parse_build",
            tool_version="0.10.2",
            objects=[
                CasObjectRecord(logical_path="a.json", role="assurance", content_address=ADDRESS_A),
                CasObjectRecord(logical_path="a.json", role="report", content_address=ADDRESS_B),
            ],
        )
