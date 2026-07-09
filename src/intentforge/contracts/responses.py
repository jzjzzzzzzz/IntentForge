"""Standard external tool response contract helpers."""

from __future__ import annotations

from typing import Any
import uuid

from pydantic import BaseModel, ConfigDict, Field

from intentforge.contracts.artifacts import ArtifactRef, artifact_refs_from_result
from intentforge.contracts.errors import ToolError, tool_error


class ValidationSummary(BaseModel):
    """Compact validation status for tool/API responses."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    valid: bool | None = None
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    warning_count: int = 0
    failed_check_ids: list[str] = Field(default_factory=list)
    summary: str = ""


class QualityGateSummary(BaseModel):
    """Compact quality gate status for harness-oriented responses."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    passed: bool | None = None
    failed_gates: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    gates: dict[str, Any] = Field(default_factory=dict)


class RunSummary(BaseModel):
    """Traceability summary for one tool/workflow run."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    request_id: str
    run_id: str | None = None
    operation: str
    object_type: str | None = None
    dry_run: bool = False
    persistent_output_dir: str | None = None


class ToolResponse(BaseModel):
    """Standard response envelope for IntentForge external tools."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ok: bool
    request_id: str
    run_id: str | None = None
    object_type: str | None = None
    operation: str
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    validation: ValidationSummary | None = None
    quality_gates: QualityGateSummary | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: ToolError | None = None
    cad_exported: bool | None = None
    dry_run: bool = False


def generate_request_id() -> str:
    """Generate a compact request ID for external workflow calls."""

    return f"req_{uuid.uuid4().hex[:16]}"


def ensure_request_id(request_id: str | None = None) -> str:
    """Return a caller-provided request ID or generate one."""

    return request_id or generate_request_id()


def validation_summary_from_report(report: Any) -> ValidationSummary:
    """Build a compact validation summary from a ValidationReport or dict."""

    if report is None:
        return ValidationSummary()
    if hasattr(report, "model_dump"):
        report = report.model_dump(mode="json")
    checks = list(report.get("checks", []) if isinstance(report, dict) else [])
    failed = [check for check in checks if check.get("status") == "fail"]
    warnings = [
        check
        for check in checks
        if check.get("status") == "warning" or check.get("severity") == "warning"
    ]
    passed_checks = sum(1 for check in checks if check.get("status") in {"pass", "warning"})
    return ValidationSummary(
        valid=bool(report.get("valid")) if "valid" in report else None,
        total_checks=len(checks),
        passed_checks=passed_checks,
        failed_checks=len(failed),
        warning_count=len(warnings),
        failed_check_ids=[str(check.get("id")) for check in failed if check.get("id")],
        summary=str(report.get("summary", "")),
    )


def quality_gate_summary_from_report(report: dict[str, Any] | None) -> QualityGateSummary | None:
    """Build a compact quality gate summary from a technical harness report."""

    if not report:
        return None
    return QualityGateSummary(
        passed=report.get("quality_gates_passed"),
        failed_gates=list(report.get("failed_gates", [])),
        metrics=dict(report.get("metrics", {})),
        gates=dict(report.get("quality_gates", {})),
    )


def error_response(
    *,
    operation: str,
    request_id: str | None = None,
    error_type: str = "InternalError",
    message: str = "Internal error.",
    recoverable: bool = True,
    suggested_action: str | None = None,
    object_type: str | None = None,
    run_id: str | None = None,
    warnings: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a JSON-compatible standard failure response."""

    request_id = ensure_request_id(request_id)
    error = tool_error(
        error_type,
        message,
        recoverable=recoverable,
        suggested_action=suggested_action,
    )
    response = ToolResponse(
        ok=False,
        request_id=request_id,
        run_id=run_id,
        object_type=object_type,
        operation=operation,
        artifacts=[],
        warnings=warnings or [],
        metadata=metadata or {},
        error=error,
        cad_exported=False,
    ).model_dump(mode="json", exclude_none=True)
    # Compatibility keys used by older CLI/MCP tests and benchmark code.
    response["error_type"] = error_type
    response["message"] = message
    return response


def apply_response_contract(
    result: dict[str, Any],
    *,
    operation: str,
    request_id: str | None = None,
    object_type: str | None = None,
    validation_report: Any | None = None,
    quality_gate_report: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Enrich a legacy workflow result with the standard response contract."""

    request_id = ensure_request_id(request_id or result.get("request_id"))
    object_type = object_type or result.get("object_type")
    result["request_id"] = request_id
    result["operation"] = operation
    result["dry_run"] = bool(dry_run or result.get("dry_run", False))
    if object_type is not None:
        result["object_type"] = object_type

    result.setdefault("warnings", [])
    result.setdefault("artifacts", [ref.model_dump(mode="json") for ref in artifact_refs_from_result(result)])

    validation_source = validation_report or result.get("validation_report")
    if validation_source is not None:
        result["validation"] = validation_summary_from_report(validation_source).model_dump(mode="json")
    elif "validation_valid" in result:
        result["validation"] = ValidationSummary(valid=bool(result["validation_valid"])).model_dump(mode="json")

    quality_gates = quality_gate_summary_from_report(quality_gate_report)
    if quality_gates is not None:
        result["quality_gates"] = quality_gates.model_dump(mode="json")

    run_summary = RunSummary(
        request_id=request_id,
        run_id=result.get("run_id"),
        operation=operation,
        object_type=object_type,
        dry_run=result["dry_run"],
        persistent_output_dir=result.get("persistent_output_dir"),
    )
    merged_metadata = dict(result.get("metadata", {}))
    merged_metadata.update(metadata or {})
    merged_metadata["run_summary"] = run_summary.model_dump(mode="json", exclude_none=True)
    result["metadata"] = merged_metadata

    if not result.get("ok", False):
        error_type = str(result.get("error_type") or "InternalError")
        message = str(result.get("message") or result.get("error") or "Request failed.")
        result["error"] = tool_error(error_type, message).model_dump(mode="json")
        result.setdefault("cad_exported", False)
        result["artifacts"] = []

    return result
