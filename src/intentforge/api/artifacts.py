"""Safe artifact file serving for IntentForge HTTP API.

Only files under the configured ``output/`` directory may be served.
Path traversal attempts (``..``, absolute paths outside output) are rejected.
"""

from __future__ import annotations

import os
from pathlib import Path

from intentforge.workflows import default_output_root


OUTPUT_ROOT = default_output_root()


def _resolve_safe_path(relative_path: str) -> Path:
    """Resolve a relative path against the output root, rejecting traversal.

    The resulting path must be inside ``output/``.  Any path that escapes
    the output directory (via ``..``, symlinks, or absolute prefix) is
    rejected.
    """

    candidate = (OUTPUT_ROOT / relative_path).resolve()
    output_resolved = OUTPUT_ROOT.resolve()

    # Reject if resolved path is not under output root.
    try:
        candidate.relative_to(output_resolved)
    except ValueError:
        raise ValueError(
            f"Path traversal rejected: '{relative_path}' resolves outside the output directory."
        )

    return candidate


def safe_artifact_path(relative_path: str) -> Path:
    """Return a validated, resolved artifact path or raise ValueError."""

    # Reject obvious traversal patterns before resolution.
    normalized = os.path.normpath(relative_path)
    if normalized.startswith("..") or normalized.startswith("/") or normalized.startswith("\\"):
        raise ValueError(
            f"Path traversal rejected: '{relative_path}' contains unsafe components."
        )

    return _resolve_safe_path(relative_path)


def serve_artifact_file(relative_path: str) -> "fastapi.responses.FileResponse":
    """Serve an artifact file if it exists and is under the output directory.

    Returns a FastAPI FileResponse; raises ValueError for path traversal
    or FileNotFoundError if the file does not exist.
    """

    try:
        from fastapi.responses import FileResponse
    except ImportError as exc:
        raise RuntimeError(
            "FastAPI is required for artifact file serving. "
            "Install it with: python -m pip install \"intentforge[api]\""
        ) from exc

    safe_path = safe_artifact_path(relative_path)

    if not safe_path.exists():
        raise FileNotFoundError(f"Artifact not found: {relative_path}")

    if not safe_path.is_file():
        raise ValueError(f"Artifact path is not a file: {relative_path}")

    # Determine media type from extension.
    ext = safe_path.suffix.lower()
    media_type_map = {
        ".step": "application/step",
        ".stp": "application/step",
        ".stl": "model/stl",
        ".json": "application/json",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".txt": "text/plain",
    }
    media_type = media_type_map.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(safe_path),
        media_type=media_type,
        filename=safe_path.name,
    )
