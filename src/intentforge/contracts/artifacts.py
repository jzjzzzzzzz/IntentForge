"""Artifact reference contract objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ArtifactKind = Literal[
    "intent_json",
    "params_yaml",
    "feature_plan_json",
    "validation_report",
    "edit_report",
    "step",
    "stl",
    "benchmark_report",
    "harness_report",
    "summary_text",
]


class ArtifactRef(BaseModel):
    """Reference to a generated or planned artifact."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    kind: ArtifactKind
    path: str = Field(..., min_length=1)
    persistent: bool = False
    object_type: str | None = None
    exists: bool | None = None
    generated: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


_OUTPUT_KIND_MAP: dict[str, ArtifactKind] = {
    "intent": "intent_json",
    "params": "params_yaml",
    "updated_params": "params_yaml",
    "feature_plan": "feature_plan_json",
    "validation_report": "validation_report",
    "shared_validation_report": "validation_report",
    "edit_report": "edit_report",
    "step": "step",
    "stl": "stl",
    "report": "harness_report",
    "summary": "summary_text",
}


def artifact_ref(
    *,
    kind: ArtifactKind,
    path: str | Path,
    persistent: bool = False,
    object_type: str | None = None,
    generated: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> ArtifactRef:
    """Build an artifact reference with existence metadata when possible."""

    path_string = str(path)
    exists: bool | None
    try:
        exists = Path(path_string).exists()
    except OSError:
        exists = None
    return ArtifactRef(
        kind=kind,
        path=path_string,
        persistent=persistent,
        object_type=object_type,
        exists=exists,
        generated=generated,
        metadata=metadata or {},
    )


def artifact_refs_from_outputs(
    *,
    latest_outputs: dict[str, Any] | None = None,
    persistent_outputs: dict[str, Any] | None = None,
    object_type: str | None = None,
    generated: bool | None = None,
) -> list[ArtifactRef]:
    """Build artifact refs from legacy workflow output-path dictionaries."""

    refs: list[ArtifactRef] = []
    for outputs, persistent in ((latest_outputs or {}, False), (persistent_outputs or {}, True)):
        for name, path in outputs.items():
            kind = _OUTPUT_KIND_MAP.get(name)
            if kind is None:
                continue
            refs.append(
                artifact_ref(
                    kind=kind,
                    path=path,
                    persistent=persistent,
                    object_type=object_type,
                    generated=generated,
                    metadata={"legacy_key": name},
                )
            )
    return refs


def artifact_refs_from_result(result: dict[str, Any]) -> list[ArtifactRef]:
    """Extract standard artifact refs from a workflow result."""

    object_type = result.get("object_type")
    cad_exported = result.get("cad_exported")
    refs = artifact_refs_from_outputs(
        latest_outputs=result.get("latest_outputs"),
        persistent_outputs=result.get("persistent_outputs"),
        object_type=object_type,
        generated=cad_exported,
    )

    path_specs: tuple[tuple[str, ArtifactKind, bool], ...] = (
        ("step_path", "step", False),
        ("stl_path", "stl", False),
        ("report_path", "validation_report", False),
        ("persistent_report_path", "validation_report", True),
        ("persistent_report", "harness_report", True),
        ("summary_path", "summary_text", False),
        ("persistent_summary_path", "summary_text", True),
    )
    existing_paths = {(ref.kind, ref.path, ref.persistent) for ref in refs}
    for key, kind, persistent in path_specs:
        path = result.get(key)
        if not path:
            continue
        identity = (kind, str(path), persistent)
        if identity in existing_paths:
            continue
        refs.append(
            artifact_ref(
                kind=kind,
                path=path,
                persistent=persistent,
                object_type=object_type,
                generated=cad_exported,
                metadata={"legacy_key": key},
            )
        )
        existing_paths.add(identity)

    planned_specs: tuple[tuple[str, ArtifactKind, bool], ...] = (
        ("latest_step", "step", False),
        ("latest_stl", "stl", False),
        ("persistent_step", "step", True),
        ("persistent_stl", "stl", True),
    )
    for key, kind, persistent in planned_specs:
        path = (result.get("planned_outputs") or {}).get(key)
        if not path:
            continue
        identity = (kind, str(path), persistent)
        if identity in existing_paths:
            continue
        refs.append(
            artifact_ref(
                kind=kind,
                path=path,
                persistent=persistent,
                object_type=object_type,
                generated=False,
                metadata={"legacy_key": key, "planned": True},
            )
        )
    return refs
