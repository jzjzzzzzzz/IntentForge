"""Pydantic request/response schemas for IntentForge HTTP API.

These models validate incoming API requests and define the shape of
responses.  All API responses are contract-compatible ToolResponse
envelopes, so these schemas primarily handle request validation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Request schemas ──────────────────────────────────────────────────


class ParseRequest(BaseModel):
    """Request body for POST /v1/parse."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prompt: str = Field(..., min_length=1)
    request_id: str | None = None
    output_root: str | None = None


class ParseBuildRequest(BaseModel):
    """Request body for POST /v1/parse-build."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prompt: str = Field(..., min_length=1)
    request_id: str | None = None
    output_root: str | None = None
    dry_run: bool = False


class EditParseRequest(BaseModel):
    """Request body for POST /v1/edit-parse."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    edit_text: str = Field(..., min_length=1)
    request_id: str | None = None
    output_root: str | None = None


class EditApplyRequest(BaseModel):
    """Request body for POST /v1/edit-apply."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    target: str = Field(..., min_length=1)
    edit_text: str = Field(..., min_length=1)
    request_id: str | None = None
    output_root: str | None = None
    dry_run: bool = False


class LlmParseRequest(BaseModel):
    """Request body for POST /v1/llm/parse."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prompt: str = Field(..., min_length=1)
    request_id: str | None = None


class LlmParseBuildRequest(BaseModel):
    """Request body for POST /v1/llm/parse-build."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    prompt: str = Field(..., min_length=1)
    request_id: str | None = None
    output_root: str | None = None
    dry_run: bool = False


class LlmEditParseRequest(BaseModel):
    """Request body for POST /v1/llm/edit-parse."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    object_type: str = Field(..., min_length=1)
    edit_text: str = Field(..., min_length=1)
    request_id: str | None = None


class LlmEditApplyRequest(BaseModel):
    """Request body for POST /v1/llm/edit-apply."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    object_type: str = Field(..., min_length=1)
    edit_text: str = Field(..., min_length=1)
    request_id: str | None = None
    output_root: str | None = None
    dry_run: bool = False


class TechnicalHarnessRequest(BaseModel):
    """Request body for POST /v1/technical-harness."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    request_id: str | None = None
    quick: bool = False
    include_demo: bool = False
    output_root: str | None = None


class ListRunsRequest(BaseModel):
    """Query parameters for GET /v1/runs/recent."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    kind: str = "parsed_runs"
    limit: int = Field(default=5, ge=1, le=100)
    output_root: str | None = None
    request_id: str | None = None


# ── Response envelope ────────────────────────────────────────────────

# API responses use the existing ToolResponse contract model from
# intentforge.contracts.responses.  No separate API response schema
# is needed — the API layer wraps workflow results into ToolResponse
# via apply_response_contract or returns raw dict results that are
# already contract-compatible.
