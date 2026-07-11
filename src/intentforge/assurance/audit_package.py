"""Portable directory-based audit packages with deterministic logical identity."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path, PurePosixPath
from typing import Any

from intentforge.assurance.renderer import render_assurance_markdown
from intentforge.assurance.schema import AssuranceCase, canonical_digest, safe_relative_path
from intentforge.assurance.validator import validate_assurance_case
from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.evidence_registry import load_evidence_definitions

REQUIRED_FILES = {
    "assurance_case.json", "assurance_case.md", "intent.json", "capability_snapshot.json",
    "evidence_snapshot.json", "validation_summary.json", "reasoning_summary.json", "artifact_manifest.json",
}
OPTIONAL_REVIEW_FILES = {
    "review_policy_snapshot.json", "review_decision.json", "review_decision.md",
}


def _tool_version() -> str:
    try:
        return version("intentforge")
    except PackageNotFoundError:
        return "source-checkout"


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_case(case: AssuranceCase | dict | str | Path) -> AssuranceCase:
    if isinstance(case, AssuranceCase): return case
    if isinstance(case, dict): return AssuranceCase.model_validate(case)
    return AssuranceCase.model_validate_json(Path(case).read_text(encoding="utf-8"))


def _logical_package_id(case: AssuranceCase, inventory: dict[str, str]) -> str:
    return canonical_digest("audit_package", {"assurance_case_id": case.assurance_case_id, "files": inventory})


def compute_audit_package_id(case: AssuranceCase | dict, inventory: dict[str, str]) -> str:
    """Return the deterministic logical package identity for an inventory."""
    return _logical_package_id(_read_case(case), dict(sorted(inventory.items())))


def build_audit_package(
    case: AssuranceCase | dict | str | Path,
    output_dir: str | Path,
    *,
    review_policy: Any | None = None,
    review_decision: Any | None = None,
) -> dict[str, Any]:
    """Write a safe metadata-focused audit package directory."""

    record = _read_case(case)
    validation = validate_assurance_case(record)
    if not validation.passed:
        raise ValueError("cannot package invalid assurance case: " + "; ".join(validation.errors))
    capabilities = {item.capability_id: item.model_dump(mode="json") for item in load_capability_manifest().capabilities}
    evidence = {item.evidence_id: item.model_dump(mode="json") for item in load_evidence_definitions()}
    payloads: dict[str, bytes] = {
        "assurance_case.json": record.to_json().encode("utf-8"),
        "assurance_case.md": render_assurance_markdown(record).encode("utf-8"),
        "intent.json": _json_bytes(record.structured_intent or record.input_request),
        "capability_snapshot.json": _json_bytes({key: capabilities[key] for key in record.capability_references}),
        "evidence_snapshot.json": _json_bytes({key: evidence[key] for key in record.evidence_references}),
        "validation_summary.json": _json_bytes([item.model_dump(mode="json") for item in record.validation_observations]),
        "reasoning_summary.json": _json_bytes(record.reasoning_summary or {"available": False}),
        "artifact_manifest.json": _json_bytes([item.model_dump(mode="json") for item in record.artifact_records]),
    }
    if (review_policy is None) != (review_decision is None):
        raise ValueError("review policy and review decision must be supplied together")
    decision_record = None
    policy_record = None
    if review_policy is not None and review_decision is not None:
        from intentforge.review.renderer import render_review_decision_markdown
        from intentforge.review.schema import ReviewDecision, ReviewPolicy
        from intentforge.review.validator import validate_review_decision, validate_review_policy

        policy_record = review_policy if isinstance(review_policy, ReviewPolicy) else ReviewPolicy.model_validate(review_policy)
        decision_record = review_decision if isinstance(review_decision, ReviewDecision) else ReviewDecision.model_validate(review_decision)
        policy_validation = validate_review_policy(policy_record)
        decision_validation = validate_review_decision(
            decision_record, policy=policy_record, assurance_case=record,
        )
        if not policy_validation.passed:
            raise ValueError("cannot package invalid review policy: " + "; ".join(policy_validation.errors))
        if not decision_validation.passed:
            raise ValueError("cannot package invalid review decision: " + "; ".join(decision_validation.errors))
        payloads.update({
            "review_policy_snapshot.json": policy_record.to_json().encode("utf-8"),
            "review_decision.json": decision_record.to_json().encode("utf-8"),
            "review_decision.md": render_review_decision_markdown(decision_record).encode("utf-8"),
        })
    inventory = {name: _sha256(data) for name, data in sorted(payloads.items())}
    package_id = _logical_package_id(record, inventory)
    manifest = {
        "schema_version": "1.0", "package_id": package_id, "assurance_case_id": record.assurance_case_id,
        "tool_version": _tool_version(), "cad_family": record.cad_family, "operation": record.operation,
        "assurance_profile": record.profile, "validation_status": record.overall_assurance_status,
        "file_inventory": inventory, "limitations": [item.limitation_id for item in record.limitations],
        "review_requirements": record.review_requirements,
    }
    if decision_record is not None and policy_record is not None:
        manifest["review_policy_id"] = policy_record.policy_id
        manifest["review_policy_version"] = policy_record.policy_version
        manifest["review_policy_content_id"] = policy_record.content_id
        manifest["review_decision_id"] = decision_record.decision_id
        manifest["review_decision_content_id"] = decision_record.content_id
        manifest["review_decision_status"] = decision_record.decision_status
    payloads["manifest.json"] = _json_bytes(manifest)
    checksums = {name: _sha256(data) for name, data in sorted(payloads.items())}
    payloads["checksums.json"] = _json_bytes(checksums)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name, data in payloads.items():
        safe_relative_path(name)
        (root / name).write_bytes(data)
    return {"package_id": package_id, "package_path": str(root), "assurance_case_id": record.assurance_case_id,
            "file_count": len(payloads), "validation": validate_audit_package(root)}


def validate_audit_package(package_path: str | Path) -> dict[str, Any]:
    root = Path(package_path)
    errors: list[str] = []
    if not root.is_dir(): return {"passed": False, "errors": ["audit package directory does not exist"]}
    names = {item.name for item in root.iterdir() if item.is_file()}
    missing = sorted(REQUIRED_FILES.union({"manifest.json", "checksums.json"}) - names)
    if missing: errors.append("missing required files: " + ", ".join(missing))
    review_files = names.intersection(OPTIONAL_REVIEW_FILES)
    if review_files and review_files != OPTIONAL_REVIEW_FILES:
        errors.append("incomplete review decision attachment")
    forbidden = [item.name for item in root.rglob("*") if any(part in {".git", ".claude", "CLAUDE.md"} for part in item.relative_to(root).parts)]
    if forbidden: errors.append("forbidden package paths: " + ", ".join(sorted(forbidden)))
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        checksums = json.loads((root / "checksums.json").read_text(encoding="utf-8"))
        case = AssuranceCase.model_validate_json((root / "assurance_case.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {"passed": False, "errors": errors + [f"invalid package data: {exc}"]}
    hash_mismatches = []
    for name, expected in checksums.items():
        try: safe_relative_path(name)
        except ValueError: errors.append(f"unsafe inventory path: {name}"); continue
        path = root / name
        if not path.is_file() or _sha256(path.read_bytes()) != expected: hash_mismatches.append(name)
    if hash_mismatches: errors.append("checksum mismatch: " + ", ".join(sorted(hash_mismatches)))
    logical_inventory = manifest.get("file_inventory", {})
    for name, expected in logical_inventory.items():
        path = root / name
        if not path.is_file() or _sha256(path.read_bytes()) != expected: errors.append(f"logical inventory mismatch: {name}")
    expected_package_id = _logical_package_id(case, logical_inventory)
    if manifest.get("package_id") != expected_package_id: errors.append("package content ID mismatch")
    if manifest.get("assurance_case_id") != case.assurance_case_id: errors.append("assurance case ID mismatch")
    case_validation = validate_assurance_case(case)
    if not case_validation.passed: errors.extend(case_validation.errors)
    review_validation_passed = None
    if review_files == OPTIONAL_REVIEW_FILES:
        try:
            from intentforge.review.schema import ReviewDecision, ReviewPolicy
            from intentforge.review.validator import validate_review_decision, validate_review_policy

            policy = ReviewPolicy.model_validate_json((root / "review_policy_snapshot.json").read_text(encoding="utf-8"))
            decision = ReviewDecision.model_validate_json((root / "review_decision.json").read_text(encoding="utf-8"))
            policy_validation = validate_review_policy(policy)
            decision_validation = validate_review_decision(decision, policy=policy, assurance_case=case)
            review_validation_passed = policy_validation.passed and decision_validation.passed
            if not policy_validation.passed:
                errors.extend(f"review policy: {item}" for item in policy_validation.errors)
            if not decision_validation.passed:
                errors.extend(f"review decision: {item}" for item in decision_validation.errors)
            if manifest.get("review_policy_id") != policy.policy_id: errors.append("review policy ID mismatch")
            if manifest.get("review_policy_version") != policy.policy_version: errors.append("review policy version mismatch")
            if manifest.get("review_policy_content_id") != policy.content_id: errors.append("review policy content ID mismatch")
            if manifest.get("review_decision_id") != decision.decision_id: errors.append("review decision ID mismatch")
            if manifest.get("review_decision_content_id") != decision.content_id: errors.append("review decision content ID mismatch")
            if manifest.get("review_decision_status") != decision.decision_status: errors.append("review decision status mismatch")
            from intentforge.review.renderer import render_review_decision_markdown
            if (root / "review_decision.md").read_text(encoding="utf-8") != render_review_decision_markdown(decision):
                errors.append("review decision Markdown mismatch")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            review_validation_passed = False
            errors.append(f"invalid review decision attachment: {exc}")
    return {"passed": not errors, "errors": errors, "package_id": manifest.get("package_id"),
            "assurance_case_id": case.assurance_case_id, "file_count": len(names),
            "hash_mismatch_count": len(hash_mismatches),
            "review_decision_attached": review_files == OPTIONAL_REVIEW_FILES,
            "review_decision_validation_passed": review_validation_passed}


def inspect_audit_package(package_path: str | Path) -> dict[str, Any]:
    root = Path(package_path)
    validation = validate_audit_package(root)
    manifest = {}
    if (root / "manifest.json").is_file():
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return {"validation": validation, "manifest": manifest, "files": sorted(item.name for item in root.iterdir() if item.is_file()) if root.is_dir() else []}


def attach_review_decision_to_audit_package(
    package_path: str | Path,
    review_policy: Any,
    review_decision: Any,
) -> dict[str, Any]:
    """Rebuild an existing package with optional review snapshots attached."""

    root = Path(package_path)
    case_path = root / "assurance_case.json"
    if not case_path.is_file():
        raise ValueError("audit package does not contain assurance_case.json")
    case = AssuranceCase.model_validate_json(case_path.read_text(encoding="utf-8"))
    return build_audit_package(
        case,
        root,
        review_policy=review_policy,
        review_decision=review_decision,
    )
