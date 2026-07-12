"""Canonical, platform-neutral serialization helpers for audit packages."""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote

from intentforge.assurance.schema import AssuranceCase, canonical_digest


PORTABILITY_PROFILE = "intentforge_portable_audit_v1"
PORTABILITY_VERSION = "1.0"
PORTABLE_REQUEST_ID = "portable_request"
PORTABLE_RUN_ID = "portable_run"
PORTABLE_PARENT_RUN_ID = "portable_parent_run"

_DRIVE_PATH = re.compile(r"^[A-Za-z]:[/\\]")
_EMBEDDED_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[/\\][^\s\"']+")
_EMBEDDED_TEMP_PATH = re.compile(
    r"(?<![A-Za-z0-9])(?:/private)?/tmp/[^\s\"']+|"
    r"(?<![A-Za-z0-9])/var/folders/[^\s\"']+",
    re.IGNORECASE,
)
_EMBEDDED_UNIX_PATH = re.compile(
    r"(?<![:A-Za-z0-9])/(?:Users|home|var|private|tmp|opt|etc|root|mnt|Volumes)/[^\s\"']+"
)
_RUNTIME_ID_KEYS = {"request_id", "run_id", "parent_run_id"}
_RUNTIME_METADATA_KEYS = {"runtime_metadata", "execution_metadata", "host_metadata"}
_TIMESTAMP_KEYS = {
    "timestamp", "created_at", "generated_at", "executed_at", "runtime_timestamp",
}
_TIMEZONE_KEYS = {"timezone", "time_zone", "local_timezone"}
_PLATFORM_KEYS = {
    "platform", "operating_system", "os_name", "system", "hostname", "machine",
    "architecture", "temp_directory", "temporary_directory",
}
_PATH_KEYS = {
    "path", "file_path", "source_path", "output_path", "package_path", "report_path",
    "artifact_path", "root_path", "working_directory", "cwd",
}


def canonical_json_bytes(value: Any) -> bytes:
    """Return the sole JSON encoding used for portable package files."""

    return (
        json.dumps(
            value,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def _fully_unquote(value: str) -> str:
    decoded = value
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            return decoded
        decoded = next_value
    return decoded


def _portable_path(value: str) -> str:
    normalized = _fully_unquote(value.strip()).replace("\\", "/")
    if not normalized:
        raise ValueError("portable path must be non-empty")
    if normalized.startswith("//"):
        parts = [part for part in normalized.split("/") if part]
    elif _DRIVE_PATH.match(normalized):
        parts = [part for part in normalized[2:].split("/") if part]
    else:
        parts = [part for part in normalized.split("/") if part]
    if "output" in parts:
        parts = parts[parts.index("output"):]
    elif normalized.startswith("/") or _DRIVE_PATH.match(normalized) or normalized.startswith("//"):
        parts = ["portable_external", parts[-1] if parts else "artifact"]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("portable path must not contain traversal")
    return PurePosixPath(*parts).as_posix()


def _portable_string(value: str, *, key: str | None) -> str:
    if key in _PATH_KEYS:
        return _portable_path(value)
    if key in _TIMESTAMP_KEYS:
        return value if value == "deterministic" else "deterministic"
    if key in _TIMEZONE_KEYS:
        return "UTC"
    if key in _PLATFORM_KEYS:
        return "platform_neutral"
    if key in _RUNTIME_ID_KEYS:
        if key == "request_id":
            return PORTABLE_REQUEST_ID
        if key == "parent_run_id":
            return PORTABLE_PARENT_RUN_ID
        return PORTABLE_RUN_ID
    return value


def normalize_portable_data(value: Any, *, key: str | None = None) -> Any:
    """Normalize runtime-only and platform-specific fields recursively."""

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for child_key in sorted(str(item) for item in value):
            child = value[child_key]
            if child_key in _RUNTIME_METADATA_KEYS:
                normalized[child_key] = {}
                continue
            if child_key == "request_id":
                normalized[child_key] = PORTABLE_REQUEST_ID
                continue
            if child_key == "run_id":
                normalized[child_key] = PORTABLE_RUN_ID
                continue
            if child_key == "parent_run_id" and child is not None:
                normalized[child_key] = PORTABLE_PARENT_RUN_ID
                continue
            normalized[child_key] = normalize_portable_data(child, key=child_key)
        return normalized
    if isinstance(value, list):
        return [normalize_portable_data(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [normalize_portable_data(item, key=key) for item in value]
    if isinstance(value, str):
        return _portable_string(value, key=key)
    return value


def portability_violations(value: Any, *, location: str = "$") -> list[str]:
    """Return deterministic diagnostics for host-dependent serialized data."""

    errors: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            child_location = f"{location}.{key}"
            if key in _RUNTIME_METADATA_KEYS and child:
                errors.append(f"{child_location}: runtime metadata must be empty")
            if key in _TIMESTAMP_KEYS and child not in {None, "", "deterministic"}:
                errors.append(f"{child_location}: runtime timestamp is not portable")
            if key in _TIMEZONE_KEYS and child not in {None, "", "UTC"}:
                errors.append(f"{child_location}: local timezone is not portable")
            if key in _PLATFORM_KEYS and child not in {None, "", "platform_neutral"}:
                errors.append(f"{child_location}: host platform metadata is not portable")
            errors.extend(portability_violations(child, location=child_location))
        return errors
    if isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(portability_violations(child, location=f"{location}[{index}]"))
        return errors
    if isinstance(value, str):
        decoded = _fully_unquote(value)
        if "\\" in decoded:
            errors.append(f"{location}: platform-specific path separator")
        if _EMBEDDED_DRIVE_PATH.search(decoded):
            errors.append(f"{location}: Windows absolute path")
        if _EMBEDDED_TEMP_PATH.search(decoded):
            errors.append(f"{location}: temporary filesystem path")
        if decoded.startswith("/") and not decoded.startswith("//"):
            errors.append(f"{location}: absolute filesystem path")
        elif _EMBEDDED_UNIX_PATH.search(decoded):
            errors.append(f"{location}: embedded absolute filesystem path")
        if any(part == ".." for part in decoded.replace("\\", "/").split("/")):
            errors.append(f"{location}: path traversal")
    return errors


def make_portable_assurance_case(case: AssuranceCase | dict[str, Any]) -> AssuranceCase:
    """Return a platform-neutral copy without changing deterministic case identity."""

    record = case if isinstance(case, AssuranceCase) else AssuranceCase.model_validate(case)
    payload = normalize_portable_data(record.model_dump(mode="json"))
    portable = AssuranceCase.model_validate(payload)
    if portable.content_id != record.content_id or portable.assurance_case_id != record.assurance_case_id:
        raise ValueError("portable assurance normalization changed deterministic assurance identity")
    violations = portability_violations(portable.model_dump(mode="json"))
    if violations:
        raise ValueError("assurance case is not portable: " + "; ".join(violations))
    return portable


def normalize_package_observation(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize an optional package observation embedded in review provenance."""

    if value is None:
        return None
    normalized = normalize_portable_data(value)
    if isinstance(normalized, dict):
        if normalized.get("package_id"):
            normalized["package_id"] = canonical_digest(
                "portable_package_observation",
                {key: item for key, item in normalized.items() if key != "package_id"},
            )
        nested = normalized.get("validation")
        if isinstance(nested, dict) and nested.get("package_id"):
            nested["package_id"] = canonical_digest(
                "portable_package_observation",
                {key: item for key, item in nested.items() if key != "package_id"},
            )
    return normalized


def policy_catalog_snapshot(manifest: Any) -> dict[str, Any]:
    """Return the canonical non-executable policy catalog snapshot."""

    payload = manifest.model_dump(mode="json", serialize_as_any=True)
    payload["policies"] = sorted(payload["policies"], key=lambda item: item["policy_id"])
    return normalize_portable_data(payload)
