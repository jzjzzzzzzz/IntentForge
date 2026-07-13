"""Typed content-addressed envelope schemas for finalized review packages."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intentforge.assurance.schema import safe_relative_path, validate_content_address


CAS_ENVELOPE_SCHEMA_VERSION = "1.0"
CasObjectRole = Literal[
    "assurance",
    "intent",
    "capability_snapshot",
    "evidence_snapshot",
    "validation",
    "reasoning",
    "artifact_manifest",
    "policy",
    "policy_catalog",
    "decision",
    "provenance",
    "report",
    "exemption_manifest",
    "exemption_evaluation",
]


def sha256_content_address(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CasObjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    logical_path: str
    role: CasObjectRole
    content_address: str

    @field_validator("logical_path")
    @classmethod
    def valid_path(cls, value: str) -> str:
        return safe_relative_path(value)

    @field_validator("content_address")
    @classmethod
    def valid_address(cls, value: str) -> str:
        return validate_content_address(value) or value


class AuditPackageCasEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: str = CAS_ENVELOPE_SCHEMA_VERSION
    hash_algorithm: Literal["sha256"] = "sha256"
    content_address: str = ""
    predecessor_hash_pointer: str | None = None
    assurance_case_id: str = Field(..., min_length=1)
    review_decision_id: str = Field(..., min_length=1)
    cad_family: str = Field(..., min_length=1)
    operation: str = Field(..., min_length=1)
    tool_version: str = Field(..., min_length=1)
    objects: list[CasObjectRecord] = Field(..., min_length=1)

    @field_validator("predecessor_hash_pointer")
    @classmethod
    def valid_predecessor(cls, value: str | None) -> str | None:
        return validate_content_address(value)

    @model_validator(mode="after")
    def validate_identity(self) -> "AuditPackageCasEnvelope":
        ordered = sorted(self.objects, key=lambda item: item.logical_path)
        paths = [item.logical_path for item in ordered]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate CAS object paths")
        if self.objects != ordered:
            object.__setattr__(self, "objects", ordered)
        expected = sha256_content_address(self.deterministic_payload())
        if self.content_address and self.content_address != expected:
            raise ValueError("audit package CAS envelope content address mismatch")
        if not self.content_address:
            object.__setattr__(self, "content_address", expected)
        return self

    def deterministic_payload(self) -> dict[str, Any]:
        data = self.model_dump(mode="json")
        data.pop("content_address", None)
        data["objects"] = sorted(data["objects"], key=lambda item: item["logical_path"])
        return data

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
