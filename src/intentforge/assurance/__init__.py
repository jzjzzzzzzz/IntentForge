"""Deterministic per-design assurance cases and audit packages."""

from intentforge.assurance.audit_package import (
    attach_review_decision_to_audit_package,
    build_audit_package,
    compute_audit_package_id,
    inspect_audit_package,
    validate_audit_package,
)
from intentforge.assurance.builder import build_assurance_case, build_assurance_from_prompt
from intentforge.assurance.comparison import compare_assurance_cases
from intentforge.assurance.lineage import attach_assurance_predecessor as attach_assurance_predecessor
from intentforge.assurance.renderer import render_assurance_markdown
from intentforge.assurance.schema import (
    ArtifactRecord,
    AssuranceArgument,
    AssuranceCase,
    AssuranceClaim,
    LimitationRecord,
    ValidationObservation,
    compute_assurance_content_id,
    load_assurance_case,
    serialize_assurance_case,
)
from intentforge.assurance.validator import validate_assurance_case


def __getattr__(name):
    """Lazy fallback that re-imports from the lineage submodule on access.

    Provides a defensive path for environments where the module was
    collected but the eager ``from ... import attach_assurance_predecessor``
    binding did not materialize.
    """

    if name == "attach_assurance_predecessor":
        from intentforge.assurance.lineage import attach_assurance_predecessor as _fn
        return _fn
    raise AttributeError(f"module 'intentforge.assurance' has no attribute {name!r}")

__all__ = [
    "ArtifactRecord",
    "AssuranceArgument",
    "AssuranceCase",
    "AssuranceClaim",
    "LimitationRecord",
    "ValidationObservation",
    "attach_review_decision_to_audit_package",
    "build_assurance_case",
    "build_assurance_from_prompt",
    "build_audit_package",
    "compute_assurance_content_id",
    "compute_audit_package_id",
    "compare_assurance_cases",
    "attach_assurance_predecessor",
    "inspect_audit_package",
    "load_assurance_case",
    "render_assurance_markdown",
    "serialize_assurance_case",
    "validate_assurance_case",
    "validate_audit_package",
]
