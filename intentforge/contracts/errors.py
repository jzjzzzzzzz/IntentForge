"""Standard tool/API error contract objects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StandardErrorType = Literal[
    "UnsupportedObjectError",
    "UnsupportedGeometryError",
    "InvalidParameterError",
    "ValidationFailedError",
    "CadBackendUnavailableError",
    "CadGenerationError",
    "EditRejectedError",
    "AmbiguousRequestError",
    "ArtifactError",
    "LLMProviderUnavailableError",
    "InternalError",
]


class ToolError(BaseModel):
    """Structured external error object for tool/API responses."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    error_type: StandardErrorType | str
    message: str = Field(..., min_length=1)
    recoverable: bool = True
    suggested_action: str = ""


def normalize_error_type(error_type: str, message: str = "") -> StandardErrorType | str:
    """Map internal exception names/messages to public contract error types."""

    lowered = message.lower()
    if error_type in {"CadQueryUnavailableError", "ImportError", "ModuleNotFoundError"}:
        return "CadBackendUnavailableError"
    if error_type == "LLMProviderUnavailableError":
        return "LLMProviderUnavailableError"
    if error_type == "UnsupportedObjectError":
        if any(token in lowered for token in ("curved", "adjustable", "sheet-metal", "freeform", "coordinates")):
            return "UnsupportedGeometryError"
        return "UnsupportedObjectError"
    if error_type == "UnsupportedEditError":
        if any(token in lowered for token in ("measurable", "ambiguous", "optimize", "better", "stronger", "cheaper")):
            return "AmbiguousRequestError"
        if any(token in lowered for token in ("curved", "adjustable", "sheet-metal", "freeform", "coordinates")):
            return "UnsupportedGeometryError"
        return "EditRejectedError"
    if error_type in {"EditRejected", "EditRejectedError"}:
        return "EditRejectedError"
    if error_type in {"ValueError", "TypeError"}:
        return "InvalidParameterError"
    if error_type in {"FileNotFoundError", "OSError", "JSONDecodeError"}:
        return "ArtifactError"
    if error_type == "ValidationFailedError":
        return "ValidationFailedError"
    return "InternalError" if error_type.endswith("Error") else error_type


def suggested_action_for_error(error_type: str, message: str = "") -> str:
    """Return a short recovery hint for common public error types."""

    normalized = normalize_error_type(error_type, message)
    if normalized == "CadBackendUnavailableError":
        return "Install the CadQuery optional dependency with: python -m pip install -e '.[cad]'."
    if normalized == "UnsupportedObjectError":
        return "Use one of the supported model families: wall_mounted_bracket or l_bracket."
    if normalized == "UnsupportedGeometryError":
        return "Use only the supported deterministic geometry options for the selected model family."
    if normalized == "InvalidParameterError":
        return "Provide numeric dimensions and constraints within the supported parameter ranges."
    if normalized == "AmbiguousRequestError":
        return "Provide a measurable parameter or explicit supported feature change."
    if normalized == "EditRejectedError":
        return "Revise the edit so it preserves supported constraints and feature intent."
    if normalized == "ValidationFailedError":
        return "Review failed validation checks and adjust parameters before exporting CAD."
    if normalized == "ArtifactError":
        return "Check that the requested artifact or run metadata path exists and is readable."
    if normalized == "LLMProviderUnavailableError":
        return "Configure an optional LLM provider or use the mock provider for deterministic local testing."
    return "Inspect the response metadata and retry with a narrower supported request."


def tool_error(
    error_type: str,
    message: str,
    *,
    recoverable: bool = True,
    suggested_action: str | None = None,
) -> ToolError:
    """Build a structured error object."""

    normalized = normalize_error_type(error_type, message)
    return ToolError(
        error_type=normalized,
        message=message or normalized,
        recoverable=recoverable,
        suggested_action=suggested_action if suggested_action is not None else suggested_action_for_error(error_type, message),
    )
