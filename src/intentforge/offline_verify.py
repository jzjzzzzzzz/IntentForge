"""Standard-library-only static verification for portable audit packages.

This module intentionally has no imports from the live IntentForge registries,
Pydantic, CadQuery, LLM providers, network clients, or manifest-selected code.
It validates only the immutable data enclosed in a Phase 26 audit package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any
from urllib.parse import unquote


OFFLINE_VERIFIER_VERSION = "1.0"
SUPPORTED_PACKAGE_SCHEMAS = {"1.1", "1.2"}
CAS_ENVELOPE_FILE = "cas_envelope.json"
EXPECTED_RULE_COUNT = 10
EXPECTED_CAPABILITY_COUNT = 28
EXPECTED_EVIDENCE_COUNT = 65
EXPECTED_POLICY_COUNT = 5
EXPECTED_POLICY_CHECK_COUNT = 54
EXPECTED_SNAPSHOT_TYPES = {
    "review_policy", "assurance_case", "rule_registry", "capability_registry",
    "evidence_registry", "evidence_resolution", "check_registry", "decision_strategy",
    "audit_package_observation", "boundary_conditions",
}
EXPECTED_POLICY_IDS = {
    "intentforge_static_review_v1",
    "intentforge_standard_design_review_v1",
    "intentforge_full_design_review_v1",
    "intentforge_edit_review_v1",
    "intentforge_safe_rejection_review_v1",
}
CHECK_TYPES = {
    "assurance_profile_allowed", "overall_assurance_status_allowed", "required_claim_present",
    "required_claim_status", "forbidden_claim_status", "maximum_partial_claim_count",
    "zero_failed_claims", "zero_unresolved_claims", "required_validation_present",
    "required_validation_status", "required_evidence_status", "required_capability_reference",
    "required_rule_reference", "artifact_integrity_required", "audit_package_valid",
    "reproducibility_required", "limitation_category_allowed", "limitation_category_forbidden",
    "limitation_requires_manual_review", "unsupported_boundary_disclosed",
    "safe_rejection_verified", "no_cad_artifact_on_rejection",
    "edit_intent_preservation_required", "required_review_disclosed",
    "minimum_assurance_profile", "schema_version_supported",
}
DECISION_PRECEDENCE = {
    "strategy": "deterministic_precedence_v1",
    "ordered_rules": [
        "required_blocking_unresolved_to_unresolved",
        "blocking_failed_to_rejected_by_policy",
        "manual_review_finding_to_manual_review_required",
        "conditional_finding_to_accepted_with_conditions",
        "all_required_checks_passed_to_accepted_within_declared_scope",
    ],
}
REQUIRED_FILES = {
    "manifest.json", "checksums.json", "assurance_case.json", "assurance_case.md",
    "intent.json", "capability_snapshot.json", "evidence_snapshot.json",
    "validation_summary.json", "reasoning_summary.json", "artifact_manifest.json",
    "review_policy_snapshot.json", "review_policy_catalog_snapshot.json",
    "review_decision.json", "review_decision.md", "review_decision_provenance.json",
}
JSON_FILES = {name for name in REQUIRED_FILES if name.endswith(".json")}
JSON_FILES.add(CAS_ENVELOPE_FILE)
FORBIDDEN_PARTS = {".git", ".claude", "claude.md", "__pycache__"}
PROFILE_RANK = {"static": 0, "standard": 1, "full": 2}
FEATURE_CAPABILITY_FLAGS = {
    "wall_rounded_corners": "rounded_corners",
    "wall_edge_fillets": "edge_fillets",
    "l_inside_fillet_intent": "inside_fillet",
}
_DRIVE_PATH = re.compile(r"^[A-Za-z]:[/\\]")
_EMBEDDED_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[/\\][^\s\"']+")
_TEMP_PATH = re.compile(r"(?:^|\s)(?:/private)?/tmp/|(?:^|\s)/var/folders/", re.IGNORECASE)
_EMBEDDED_UNIX_PATH = re.compile(
    r"(?<![:A-Za-z0-9])/(?:Users|home|var|private|tmp|opt|etc|root|mnt|Volumes)/[^\s\"']+"
)


@dataclass(frozen=True)
class OfflineVerificationResult:
    passed: bool
    status: str
    failure_stage: str | None = None
    package_id: str | None = None
    assurance_case_id: str | None = None
    decision_id: str | None = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metrics: dict[str, int | bool | str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "status": self.status,
            "failure_stage": self.failure_stage,
            "package_id": self.package_id,
            "assurance_case_id": self.assurance_case_id,
            "decision_id": self.decision_id,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": dict(sorted(self.metrics.items())),
            "offline_verifier_version": OFFLINE_VERIFIER_VERSION,
        }

    def to_json(self) -> str:
        return _canonical_json_bytes(self.to_dict()).decode("utf-8")


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True, separators=(",", ": "))
        + "\n"
    ).encode("utf-8")


def _digest(prefix: str, payload: Any, length: int = 16) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{prefix}_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:length]}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json_bytes(data: bytes, name: str) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name}: invalid UTF-8: {exc}") from exc
    try:
        return json.loads(text, object_pairs_hook=_pairs_no_duplicates)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name}: invalid JSON: {exc}") from exc


def _safe_name(name: str) -> bool:
    decoded = name
    for _ in range(4):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    normalized = decoded.replace("\\", "/")
    path = PurePosixPath(normalized)
    return bool(
        normalized
        and "/" not in normalized
        and not path.is_absolute()
        and not _DRIVE_PATH.match(normalized)
        and ".." not in path.parts
        and normalized.lower() not in FORBIDDEN_PARTS
    )


def _portability_errors(value: Any, location: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key in sorted(value):
            child = value[key]
            child_location = f"{location}.{key}"
            if key in {"runtime_metadata", "execution_metadata", "host_metadata"} and child:
                errors.append(f"{child_location}: runtime metadata is not empty")
            if key in {"timestamp", "created_at", "generated_at", "executed_at"} and child not in {
                None, "", "deterministic"
            }:
                errors.append(f"{child_location}: runtime timestamp is not portable")
            if key in {"timezone", "time_zone", "local_timezone"} and child not in {None, "", "UTC"}:
                errors.append(f"{child_location}: local timezone is not portable")
            errors.extend(_portability_errors(child, child_location))
        return errors
    if isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_portability_errors(child, f"{location}[{index}]"))
        return errors
    if isinstance(value, str):
        decoded = value
        for _ in range(4):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        if "\\" in decoded:
            errors.append(f"{location}: platform-specific path separator")
        if _EMBEDDED_DRIVE_PATH.search(decoded):
            errors.append(f"{location}: Windows absolute path")
        if _TEMP_PATH.search(decoded):
            errors.append(f"{location}: temporary filesystem path")
        if decoded.startswith("/"):
            errors.append(f"{location}: absolute filesystem path")
        elif _EMBEDDED_UNIX_PATH.search(decoded):
            errors.append(f"{location}: embedded absolute filesystem path")
        if ".." in decoded.replace("\\", "/").split("/"):
            errors.append(f"{location}: path traversal")
    return errors


def _result(
    *,
    errors: list[str],
    stage: str | None,
    manifest: dict[str, Any] | None = None,
    decision: dict[str, Any] | None = None,
    metrics: dict[str, int | bool | str] | None = None,
    warnings: list[str] | None = None,
) -> OfflineVerificationResult:
    return OfflineVerificationResult(
        passed=not errors,
        status="verified" if not errors else "failed",
        failure_stage=stage if errors else None,
        package_id=None if manifest is None else manifest.get("package_id"),
        assurance_case_id=None if manifest is None else manifest.get("assurance_case_id"),
        decision_id=None if decision is None else decision.get("decision_id"),
        errors=tuple(errors),
        warnings=tuple(warnings or []),
        metrics=metrics or {},
    )


def _without(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    result = dict(data)
    for key in keys:
        result.pop(key, None)
    return result


def _assurance_payload(case: dict[str, Any]) -> dict[str, Any]:
    data = _without(
        case,
        "assurance_case_id", "content_id", "runtime_metadata", "request_id", "run_id", "parent_run_id",
    )
    if data.get("predecessor_hash_pointer") is None:
        data.pop("predecessor_hash_pointer", None)
    for claim in data.get("claims", []):
        if claim.get("predecessor_hash_pointer") is None:
            claim.pop("predecessor_hash_pointer", None)
    for argument in data.get("arguments", []):
        if argument.get("predecessor_hash_pointer") is None:
            argument.pop("predecessor_hash_pointer", None)
    data["artifact_records"] = []
    for artifact in case.get("artifact_records", []):
        data["artifact_records"].append(
            _without(artifact, "request_id", "run_id", "content_hash", "size", "metadata_id")
        )
    return data


def _claim_identities(claim: dict[str, Any]) -> tuple[str, str, str, str]:
    base = {
        "claim_type": claim["claim_type"],
        "family": claim["family"],
        "status": claim["status"],
        "stages": sorted(claim.get("stages", [])),
        "required_review": bool(claim.get("required_review", False)),
        "capability_ids": sorted(claim.get("capability_ids", [])),
        "evidence_ids": sorted(claim.get("supporting_evidence_ids", [])),
        "validation_ids": sorted(claim.get("supporting_validation_ids", [])),
        "artifact_ids": sorted(claim.get("supporting_artifact_ids", [])),
        "rule_ids": sorted(claim.get("rule_ids", [])),
        "limitations": sorted(claim.get("limitations", [])),
    }
    if claim.get("predecessor_hash_pointer") is not None:
        base["predecessor_hash_pointer"] = claim["predecessor_hash_pointer"]
    claim_id = _digest("claim", base)
    argument_payload = {
        "claim_id": claim_id,
        "rationale_code": f"{claim['claim_type']}_evidence",
        **base,
    }
    argument_id = _digest("argument", argument_payload)
    argument_content = _digest("argument_content", argument_payload)
    claim_payload = {
        **base,
        "claim_id": claim_id,
        "argument_ids": [argument_id],
        "statement": claim["statement"],
    }
    return claim_id, _digest("claim_content", claim_payload), argument_id, argument_content


def _validate_assurance_case(
    case: dict[str, Any], capability_ids: set[str], evidence_ids: set[str], rule_ids: set[str]
) -> list[str]:
    errors: list[str] = []
    claims = case.get("claims", [])
    arguments = case.get("arguments", [])
    validations = case.get("validation_observations", [])
    artifacts = case.get("artifact_records", [])
    limitations = case.get("limitations", [])
    predecessor = case.get("predecessor_hash_pointer")
    if predecessor is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", str(predecessor)):
        errors.append("assurance case predecessor content address is malformed")
    id_groups = {
        "claim": [item.get("claim_id") for item in claims],
        "argument": [item.get("argument_id") for item in arguments],
        "validation": [item.get("validation_id") for item in validations],
        "artifact": [item.get("artifact_id") for item in artifacts],
        "limitation": [item.get("limitation_id") for item in limitations],
    }
    for label, values in id_groups.items():
        if None in values or len(values) != len(set(values)):
            errors.append(f"invalid or duplicate assurance {label} IDs")
    argument_by_id = {item.get("argument_id"): item for item in arguments}
    validation_set = set(id_groups["validation"])
    artifact_set = set(id_groups["artifact"])
    for claim in claims:
        try:
            claim_id, claim_content, argument_id, argument_content = _claim_identities(claim)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"malformed assurance claim: {exc}")
            continue
        if claim.get("claim_id") != claim_id or claim.get("content_id") != claim_content:
            errors.append(f"claim identity mismatch: {claim.get('claim_id')}")
        if claim.get("argument_ids") != [argument_id]:
            errors.append(f"claim argument index mismatch: {claim.get('claim_id')}")
        argument = argument_by_id.get(argument_id)
        if argument is None:
            errors.append(f"claim references missing argument: {claim.get('claim_id')}")
        elif argument.get("content_id") != argument_content or argument.get("claim_id") != claim_id:
            errors.append(f"argument identity mismatch: {argument_id}")
        elif argument.get("predecessor_hash_pointer") != predecessor:
            errors.append(f"argument predecessor pointer mismatch: {argument_id}")
        if claim.get("predecessor_hash_pointer") != predecessor:
            errors.append(f"claim predecessor pointer mismatch: {claim.get('claim_id')}")
        if set(claim.get("supporting_validation_ids", [])) - validation_set:
            errors.append(f"claim references unknown validation: {claim.get('claim_id')}")
        if set(claim.get("supporting_artifact_ids", [])) - artifact_set:
            errors.append(f"claim references unknown artifact: {claim.get('claim_id')}")
    if set(case.get("capability_references", [])) - capability_ids:
        errors.append("assurance case contains unknown capability references")
    if set(case.get("evidence_references", [])) - evidence_ids:
        errors.append("assurance case contains unknown evidence references")
    referenced_rules = {str(item.get("rule_id")) for item in case.get("rule_references", [])}
    if referenced_rules - rule_ids:
        errors.append("assurance case contains unknown rule references")
    for artifact in artifacts:
        path = str(artifact.get("path", ""))
        normalized = path.replace("\\", "/")
        if (
            not normalized
            or normalized.startswith("/")
            or _DRIVE_PATH.match(normalized)
            or ".." in normalized.split("/")
        ):
            errors.append(f"unsafe artifact path: {path}")
    expected_content = _digest("assurance_content", _assurance_payload(case))
    if case.get("content_id") != expected_content:
        errors.append("assurance content ID mismatch")
    if case.get("assurance_case_id") != _digest("assurance_case", {"content_id": expected_content}):
        errors.append("assurance case ID mismatch")
    return errors


def _check_payload(check: dict[str, Any]) -> dict[str, Any]:
    return _without(check, "content_id")


def _policy_payload(policy: dict[str, Any]) -> dict[str, Any]:
    data = _without(policy, "content_id")
    data["checks"] = sorted(data.get("checks", []), key=lambda item: item.get("check_id", ""))
    return data


def _validate_policy_catalog(catalog: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    policies = catalog.get("policies")
    if not isinstance(policies, list):
        return ["policy catalog does not contain a policy list"], {}
    by_id: dict[str, dict[str, Any]] = {}
    check_count = 0
    for policy in policies:
        policy_id = policy.get("policy_id")
        if not isinstance(policy_id, str) or policy_id in by_id:
            errors.append(f"invalid or duplicate review policy ID: {policy_id}")
            continue
        by_id[policy_id] = policy
        checks = policy.get("checks", [])
        check_ids = [item.get("check_id") for item in checks]
        if len(check_ids) != len(set(check_ids)):
            errors.append(f"duplicate check IDs in policy: {policy_id}")
        if checks != sorted(checks, key=lambda item: item.get("check_id", "")):
            errors.append(f"non-deterministic check order in policy: {policy_id}")
        for check in checks:
            check_count += 1
            if check.get("check_type") not in CHECK_TYPES:
                errors.append(f"unsupported policy check type: {check.get('check_type')}")
            if check.get("content_id") != _digest("policy_check", _check_payload(check)):
                errors.append(f"policy check content ID mismatch: {check.get('check_id')}")
        if policy.get("content_id") != _digest("review_policy", _policy_payload(policy)):
            errors.append(f"review policy content ID mismatch: {policy_id}")
    if set(by_id) != EXPECTED_POLICY_IDS:
        errors.append("policy catalog built-in policy set mismatch")
    if len(by_id) != EXPECTED_POLICY_COUNT:
        errors.append(f"policy catalog count mismatch: expected {EXPECTED_POLICY_COUNT}")
    if check_count != EXPECTED_POLICY_CHECK_COUNT:
        errors.append(f"policy check count mismatch: expected {EXPECTED_POLICY_CHECK_COUNT}")
    return errors, by_id


def _claims(case: dict[str, Any], kinds: list[str] | None = None) -> list[dict[str, Any]]:
    selected = case.get("claims", [])
    if kinds is not None:
        selected = [item for item in selected if item.get("claim_type") in kinds]
    return sorted(selected, key=lambda item: item.get("claim_id", ""))


def _claim_refs(claims: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "claim_ids": sorted(item.get("claim_id") for item in claims),
        "argument_ids": sorted({child for item in claims for child in item.get("argument_ids", [])}),
        "validation_ids": sorted({child for item in claims for child in item.get("supporting_validation_ids", [])}),
        "capability_ids": sorted({child for item in claims for child in item.get("capability_ids", [])}),
        "evidence_ids": sorted({child for item in claims for child in item.get("supporting_evidence_ids", [])}),
        "rule_ids": sorted({child for item in claims for child in item.get("rule_ids", [])}),
        "artifact_ids": sorted({child for item in claims for child in item.get("supporting_artifact_ids", [])}),
    }


def _validations(case: dict[str, Any], kinds: list[str]) -> list[dict[str, Any]]:
    return sorted(
        [item for item in case.get("validation_observations", []) if item.get("validation_type") in kinds],
        key=lambda item: (item.get("validation_type", ""), item.get("validation_id", "")),
    )


def _validation_refs(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "validation_ids": sorted(item.get("validation_id") for item in items),
        "artifact_ids": sorted({child for item in items for child in item.get("artifact_ids", [])}),
        "rule_ids": sorted({child for item in items for child in item.get("rule_ids", [])}),
    }


def _limitation_refs(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "limitation_ids": sorted(item.get("limitation_id") for item in items),
        "capability_ids": sorted({child for item in items for child in item.get("capability_ids", [])}),
        "rule_ids": sorted({child for item in items for child in item.get("rule_ids", [])}),
    }


def _feature_requested(case: dict[str, Any], capability_id: str) -> bool | None:
    flag_name = FEATURE_CAPABILITY_FLAGS.get(capability_id)
    if flag_name is None:
        return False
    intent = case.get("structured_intent") or {}
    metadata = intent.get("metadata") if isinstance(intent, dict) else None
    flags = metadata.get("feature_flags") if isinstance(metadata, dict) else None
    if not isinstance(flags, dict) or not isinstance(flags.get(flag_name), dict):
        return None
    return flags[flag_name].get("state") == "requested_by_user"


def _relevant_limitations(case: dict[str, Any], params: dict[str, Any]):
    selected = [item for item in case.get("limitations", []) if item.get("significance") in params.get("categories", [])]
    if params.get("capability_ids"):
        selected = [item for item in selected if set(item.get("capability_ids", [])).intersection(params["capability_ids"])]
    if not params.get("only_when_exercised"):
        return selected, []
    relevant, unresolved = [], []
    for item in selected:
        states = [_feature_requested(case, cap) for cap in item.get("capability_ids", [])]
        if any(state is True for state in states):
            relevant.append(item)
        elif any(state is None for state in states):
            unresolved.append(item)
    return relevant, unresolved


def _evaluation(status: str, observed: Any, expected: Any, **refs: Any) -> dict[str, Any]:
    value = {
        "status": status,
        "observed_value": observed,
        "expected_value": expected,
        "claim_ids": [], "argument_ids": [], "validation_ids": [], "capability_ids": [],
        "evidence_ids": [], "rule_ids": [], "limitation_ids": [], "artifact_ids": [],
        "diagnostics": [],
    }
    value.update(refs)
    return value


def _evaluate_check(
    check: dict[str, Any], case: dict[str, Any], definitions: list[dict[str, Any]],
    observations: list[dict[str, Any]], package_result: dict[str, Any] | None,
) -> dict[str, Any]:
    kind = check["check_type"]
    params = check.get("parameters", {})
    if kind == "assurance_profile_allowed":
        return _evaluation("passed" if case["profile"] in params["allowed_profiles"] else "failed", case["profile"], params["allowed_profiles"])
    if kind == "minimum_assurance_profile":
        passed = PROFILE_RANK[case["profile"]] >= PROFILE_RANK[params["minimum_profile"]]
        return _evaluation("passed" if passed else "failed", case["profile"], params["minimum_profile"])
    if kind == "overall_assurance_status_allowed":
        passed = case["overall_assurance_status"] in params["allowed_statuses"]
        return _evaluation("passed" if passed else "failed", case["overall_assurance_status"], params["allowed_statuses"])
    if kind == "required_claim_present":
        selected = _claims(case, params["claim_types"])
        present = {item["claim_type"] for item in selected}
        missing = sorted(set(params["claim_types"]) - present)
        return _evaluation("unresolved" if missing else "passed", {"present": sorted(present), "missing": missing}, {"required": sorted(params["claim_types"])}, diagnostics=[f"missing claim type: {item}" for item in missing], **_claim_refs(selected))
    if kind == "required_claim_status":
        selected = _claims(case, params["claim_types"])
        by_type = {item["claim_type"]: item for item in selected}
        missing = sorted(set(params["claim_types"]) - set(by_type))
        disallowed = sorted(item["claim_type"] for item in selected if item["status"] not in params["allowed_statuses"])
        status = "unresolved" if missing else "failed" if disallowed else "passed"
        return _evaluation(status, {"statuses": {item: by_type[item]["status"] for item in sorted(by_type)}, "missing": missing}, {"required_claim_types": sorted(params["claim_types"]), "allowed_statuses": sorted(params["allowed_statuses"])}, diagnostics=[f"missing claim type: {item}" for item in missing] + [f"disallowed claim status: {item}" for item in disallowed], **_claim_refs(selected))
    if kind == "forbidden_claim_status":
        selected = [item for item in case.get("claims", []) if item["status"] in params["forbidden_statuses"]]
        return _evaluation("failed" if selected else "passed", {"matching_claim_count": len(selected), "statuses": sorted({item["status"] for item in selected})}, {"forbidden_statuses": sorted(params["forbidden_statuses"])}, **_claim_refs(selected))
    if kind == "maximum_partial_claim_count":
        selected = [item for item in case.get("claims", []) if item["status"] == "partially_supported"]
        return _evaluation("passed" if len(selected) <= params["maximum"] else "failed", len(selected), params["maximum"], **_claim_refs(selected))
    if kind in {"zero_failed_claims", "zero_unresolved_claims"}:
        target = "failed" if kind == "zero_failed_claims" else "unresolved"
        selected = [item for item in case.get("claims", []) if item["status"] == target]
        return _evaluation("failed" if selected else "passed", len(selected), 0, **_claim_refs(selected))
    if kind == "required_validation_present":
        selected = _validations(case, params["validation_types"])
        present = {item["validation_type"] for item in selected}
        missing = sorted(set(params["validation_types"]) - present)
        return _evaluation("unresolved" if missing else "passed", {"present": sorted(present), "missing": missing}, {"required": sorted(params["validation_types"])}, diagnostics=[f"missing validation type: {item}" for item in missing], **_validation_refs(selected))
    if kind == "required_validation_status":
        selected = _validations(case, params["validation_types"])
        by_type = {item["validation_type"]: item for item in selected}
        missing = sorted(set(params["validation_types"]) - set(by_type))
        disallowed = sorted(item["validation_type"] for item in selected if item["status"] not in params["allowed_statuses"])
        status = "unresolved" if missing else "failed" if disallowed else "passed"
        return _evaluation(status, {"statuses": {item: by_type[item]["status"] for item in sorted(by_type)}, "missing": missing}, {"required_validation_types": sorted(params["validation_types"]), "allowed_statuses": sorted(params["allowed_statuses"])}, diagnostics=[f"missing validation type: {item}" for item in missing] + [f"disallowed validation status: {item}" for item in disallowed], **_validation_refs(selected))
    if kind == "required_evidence_status":
        target_ids = sorted(set(params.get("evidence_ids") or case.get("evidence_references", [])))
        if not target_ids:
            return _evaluation("unresolved", {"evidence_ids": []}, {"allowed_statuses": params["allowed_statuses"]}, diagnostics=["no evidence references supplied"])
        case_missing = sorted(set(params.get("evidence_ids", [])) - set(case.get("evidence_references", []))) if params.get("evidence_ids") else []
        definition_ids = {str(item.get("evidence_id")) for item in definitions if item.get("evidence_id") in target_ids}
        unknown = sorted(set(target_ids) - definition_ids)
        if case_missing or unknown:
            return _evaluation("unresolved", {"case_missing": case_missing, "unknown": unknown}, {"allowed_statuses": sorted(params["allowed_statuses"])}, evidence_ids=target_ids, diagnostics=[f"evidence not referenced by case: {item}" for item in case_missing] + [f"unknown evidence: {item}" for item in unknown])
        statuses = {str(item["evidence_id"]): item.get("status") for item in observations if item.get("evidence_id") in target_ids}
        disallowed = sorted(item for item, status in statuses.items() if status not in params["allowed_statuses"])
        return _evaluation("failed" if disallowed else "passed", {"statuses": {item: statuses[item] for item in sorted(statuses)}}, {"allowed_statuses": sorted(params["allowed_statuses"])}, evidence_ids=target_ids, diagnostics=[f"disallowed evidence status: {item}" for item in disallowed])
    if kind in {"required_capability_reference", "required_rule_reference"}:
        key = "capability_ids" if kind == "required_capability_reference" else "rule_ids"
        available = set(case.get("capability_references", [])) if key == "capability_ids" else {str(item.get("rule_id")) for item in case.get("rule_references", [])}
        missing = sorted(set(params[key]) - available)
        present = sorted(set(params[key]).intersection(available))
        return _evaluation("unresolved" if missing else "passed", {"present": present, "missing": missing}, {"required": sorted(params[key])}, diagnostics=[f"missing {key[:-4]} reference: {item}" for item in missing], **{key: present})
    if kind == "artifact_integrity_required":
        artifacts = sorted(case.get("artifact_records", []), key=lambda item: item["artifact_id"])
        claims = _claims(case, ["artifact_integrity_verified"])
        missing_artifacts = params.get("require_artifacts", True) and not artifacts
        unhashed = [item["artifact_id"] for item in artifacts if not item.get("content_hash")]
        bad_status = [item["artifact_id"] for item in artifacts if item.get("validation_status") != "verified"]
        missing_claim = params.get("require_integrity_claim", True) and not any(item["status"] == "supported" for item in claims)
        status = "unresolved" if missing_artifacts or missing_claim else "failed" if (params.get("require_all_hashed", True) and unhashed) or bad_status else "passed"
        refs = _claim_refs(claims); refs["artifact_ids"] = sorted({*refs["artifact_ids"], *(item["artifact_id"] for item in artifacts)})
        return _evaluation(status, {"artifact_count": len(artifacts), "content_hashes": {item["artifact_id"]: item.get("content_hash") for item in artifacts}, "unhashed": sorted(unhashed), "invalid_status": sorted(bad_status), "integrity_claim": bool(claims)}, {"artifacts_required": params.get("require_artifacts", True), "all_hashed": params.get("require_all_hashed", True), "integrity_claim_required": params.get("require_integrity_claim", True)}, diagnostics=([] if artifacts else ["no artifact records"]) + [f"unhashed artifact: {item}" for item in sorted(unhashed)] + [f"artifact integrity not verified: {item}" for item in sorted(bad_status)] + (["artifact integrity claim missing"] if missing_claim else []), **refs)
    if kind == "audit_package_valid":
        if package_result is None:
            return _evaluation("unresolved" if params.get("require_package", True) else "not_checked", None, {"passed": True}, diagnostics=["audit package result not supplied"])
        passed = bool(package_result.get("passed", package_result.get("validation", {}).get("passed", False)))
        return _evaluation("passed" if passed else "failed", {"passed": passed, "package_id": package_result.get("package_id") or package_result.get("validation", {}).get("package_id")}, {"passed": True}, diagnostics=list(package_result.get("errors", package_result.get("validation", {}).get("errors", [])) or []))
    if kind == "reproducibility_required":
        deterministic = case.get("reproducibility_metadata", {}).get("deterministic") is True
        supplied = package_result is not None
        package_passed = bool(package_result and package_result.get("passed", package_result.get("validation", {}).get("passed", False)))
        if params.get("require_valid_audit_package", True) and not supplied: status = "unresolved"
        elif (params.get("require_deterministic_metadata", True) and not deterministic) or (params.get("require_valid_audit_package", True) and not package_passed): status = "failed"
        else: status = "passed"
        return _evaluation(status, {"deterministic_metadata": deterministic, "audit_package_supplied": supplied, "audit_package_valid": package_passed}, {"deterministic_metadata": params.get("require_deterministic_metadata", True), "valid_audit_package": params.get("require_valid_audit_package", True)}, diagnostics=["valid audit package result not supplied"] if status == "unresolved" else [])
    if kind == "limitation_category_allowed":
        selected = case.get("limitations", [])
        if params.get("capability_ids"): selected = [item for item in selected if set(item.get("capability_ids", [])).intersection(params["capability_ids"])]
        disallowed = [item for item in selected if item["significance"] not in params["categories"]]
        return _evaluation("failed" if disallowed else "passed", {"disallowed_categories": sorted({item["significance"] for item in disallowed})}, {"allowed_categories": sorted(params["categories"])}, **_limitation_refs(disallowed))
    if kind in {"limitation_category_forbidden", "limitation_requires_manual_review"}:
        selected, unresolved = _relevant_limitations(case, params)
        expected_key = "forbidden_categories" if kind == "limitation_category_forbidden" else "manual_review_categories"
        expected = {expected_key: sorted(params["categories"])}
        if unresolved and (kind == "limitation_category_forbidden" or not selected):
            return _evaluation("unresolved", {"unresolved_count": len(unresolved)}, expected, **_limitation_refs(unresolved))
        if kind == "limitation_category_forbidden":
            return _evaluation("failed" if selected else "passed", {"matching_count": len(selected)}, expected, **_limitation_refs(selected))
        if not selected: return _evaluation("not_applicable", {"matching_count": 0}, expected)
        return _evaluation("failed", {"matching_count": len(selected), "limitations": [item["title"] for item in selected]}, expected, **_limitation_refs(selected))
    if kind == "unsupported_boundary_disclosed":
        selected = [item for item in case.get("limitations", []) if item["significance"] == "unsupported_boundary"]
        return _evaluation("passed" if len(selected) >= params.get("minimum_count", 1) else "failed", len(selected), {"minimum_count": params.get("minimum_count", 1)}, **_limitation_refs(selected))
    if kind == "safe_rejection_verified":
        claims = _claims(case, ["unsupported_behavior_rejected"])
        supported = any(item["status"] == "supported" for item in claims)
        error = case.get("input_request", {}).get("error")
        structured = isinstance(error, dict) and bool(error.get("error_type")) and bool(error.get("message"))
        boundaries = [item for item in case.get("limitations", []) if item["significance"] == "unsupported_boundary"]
        definition_map = {item["evidence_id"]: item for item in definitions}
        boundary_evidence = [item for item in case.get("evidence_references", []) if item in definition_map and definition_map[item].get("role") == "boundary"]
        missing = []
        if not supported: missing.append("supported rejection claim")
        if params.get("require_structured_error", True) and not structured: missing.append("structured rejection error")
        if params.get("require_boundary", True) and not boundaries: missing.append("unsupported boundary")
        if params.get("require_rejection_evidence", True) and not boundary_evidence: missing.append("boundary evidence")
        refs = _claim_refs(claims); refs["limitation_ids"] = sorted(item["limitation_id"] for item in boundaries); refs["capability_ids"] = sorted({*refs["capability_ids"], *(cap for item in boundaries for cap in item.get("capability_ids", []))}); refs["evidence_ids"] = sorted({*refs["evidence_ids"], *boundary_evidence})
        return _evaluation("unresolved" if missing else "passed", {"supported_rejection_claim": supported, "structured_error": structured, "boundary_count": len(boundaries), "boundary_evidence_count": len(boundary_evidence)}, {"all_required": True}, diagnostics=[f"missing {item}" for item in missing], **refs)
    if kind == "no_cad_artifact_on_rejection":
        artifacts = sorted(case.get("artifact_records", []), key=lambda item: item["artifact_id"])
        geometry = _claims(case, ["geometry_generated", "geometry_valid"])
        bad = [item for item in geometry if item["status"] == "supported"] if params.get("forbid_geometry_claims", True) else []
        refs = _claim_refs(bad); refs["artifact_ids"] = sorted({*refs["artifact_ids"], *(item["artifact_id"] for item in artifacts)})
        return _evaluation("failed" if artifacts or bad else "passed", {"artifact_count": len(artifacts), "successful_geometry_claim_count": len(bad)}, {"artifact_count": 0, "successful_geometry_claim_count": 0}, **refs)
    if kind == "edit_intent_preservation_required":
        claims = _claims(case, ["requested_edit_preserved_intent"])
        supported = any(item["status"] == "supported" for item in claims)
        trace = case.get("input_request", {}).get("edit_trace")
        changed = trace.get("changed_parameters") if isinstance(trace, dict) else None
        preserved = trace.get("preserved_parameters") if isinstance(trace, dict) else None
        missing = []
        if not claims: missing.append("intent-preservation claim")
        if params.get("require_parent_run_id") and not case.get("parent_run_id"): missing.append("parent run ID")
        if params.get("require_change_trace", True) and not changed: missing.append("changed-parameter trace")
        if params.get("require_preservation_trace", True) and not preserved: missing.append("preserved-parameter trace")
        status = "failed" if claims and not supported else "unresolved" if missing else "passed"
        return _evaluation(status, {"claim_supported": supported, "parent_run_id_present": bool(case.get("parent_run_id")), "changed_parameter_count": len(changed or []), "preserved_parameter_count": len(preserved or [])}, {"preservation_claim": True, "parent_run_id": params.get("require_parent_run_id", False), "change_trace": params.get("require_change_trace", True), "preservation_trace": params.get("require_preservation_trace", True)}, diagnostics=[f"missing {item}" for item in missing], **_claim_refs(claims))
    if kind == "required_review_disclosed":
        count = len(case.get("review_requirements", [])); minimum = params.get("minimum_count", 1)
        return _evaluation("passed" if count >= minimum else "failed", count, {"minimum_count": minimum})
    if kind == "schema_version_supported":
        return _evaluation("passed" if case["schema_version"] in params.get("supported_versions", ["1.0"]) else "failed", case["schema_version"], params.get("supported_versions", ["1.0"]))
    raise ValueError(f"unsupported policy check type: {kind}")


def _finding(check: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    status = evaluation["status"]
    summary = check["on_pass"] if status == "passed" else check["on_failure"] if status == "failed" else check["on_unresolved"] if status in {"unresolved", "not_checked"} else "This check does not apply to the reviewed assurance case."
    payload = {
        "check_id": check["check_id"], "status": status, "severity": check["severity"],
        "title": check["title"], "summary": summary,
        "observed_value": evaluation["observed_value"], "expected_value": evaluation["expected_value"],
        **{key: sorted(set(evaluation.get(key, []))) for key in (
            "claim_ids", "argument_ids", "validation_ids", "capability_ids", "evidence_ids",
            "rule_ids", "limitation_ids", "artifact_ids", "diagnostics",
        )},
    }
    content_id = _digest("policy_finding_content", payload)
    return {"finding_id": _digest("policy_finding", {"content_id": content_id}), **payload, "content_id": content_id}


def _condition_type(check: dict[str, Any]) -> str:
    kind = check["check_type"]
    if kind == "artifact_integrity_required": return "artifact_integrity_required"
    if kind in {"reproducibility_required", "audit_package_valid"}: return "reproducibility_check_required"
    if kind.startswith("limitation_"): return "external_review_required" if check["severity"] == "manual_review" else "limitation_acknowledgement_required"
    if kind in {"safe_rejection_verified", "no_cad_artifact_on_rejection", "unsupported_boundary_disclosed"}: return "unsupported_scope_correction_required"
    if kind in {"required_claim_present", "required_claim_status", "edit_intent_preservation_required"}: return "intent_clarification_required"
    return "additional_validation_required"


def _condition(check: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any] | None:
    if finding["status"] not in {"failed", "unresolved", "not_checked"} or check["severity"] not in {"conditional", "manual_review", "blocking"}:
        return None
    payload = {
        "source_check_id": check["check_id"], "title": check["title"], "description": finding["summary"],
        "condition_type": _condition_type(check), "blocking": check["severity"] == "blocking",
        "required_action": check["on_unresolved"] if finding["status"] in {"unresolved", "not_checked"} else check["on_failure"],
        "related_claim_ids": finding["claim_ids"], "related_validation_ids": finding["validation_ids"],
        "related_limitation_ids": finding["limitation_ids"],
    }
    content_id = _digest("acceptance_condition_content", payload)
    return {"condition_id": _digest("acceptance_condition", {"content_id": content_id}), **payload, "content_id": content_id}


def _decision_status(policy: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    checks = {item["check_id"]: item for item in policy["checks"]}
    if any(item["status"] in {"unresolved", "not_checked"} and item["severity"] == "blocking" and checks[item["check_id"]].get("required", True) for item in findings): return "unresolved"
    if any(item["status"] == "failed" and item["severity"] == "blocking" for item in findings): return "rejected_by_policy"
    if any(item["status"] in {"failed", "unresolved", "not_checked"} and item["severity"] == "manual_review" for item in findings): return "manual_review_required"
    if any(item["status"] in {"failed", "unresolved", "not_checked"} and item["severity"] == "conditional" for item in findings): return "accepted_with_conditions"
    return "accepted_within_declared_scope"


def _subject_type(case: dict[str, Any]) -> str:
    if any(item.get("claim_type") == "unsupported_behavior_rejected" for item in case.get("claims", [])): return "safe_rejection"
    if str(case.get("operation", "")).startswith("edit_"): return "edit_result"
    return "design_result"


def _decision_payload(decision: dict[str, Any]) -> dict[str, Any]:
    data = _without(decision, "decision_id", "content_id", "runtime_metadata")
    if data.get("predecessor_hash_pointer") is None:
        data.pop("predecessor_hash_pointer", None)
    provenance = data.get("decision_provenance")
    if provenance is None:
        data.pop("decision_provenance", None)
    else:
        data["decision_provenance"] = {"provenance_id": provenance["provenance_id"], "content_id": provenance["content_id"]}
    data["findings"] = sorted(data.get("findings", []), key=lambda item: item["finding_id"])
    data["conditions"] = sorted(data.get("conditions", []), key=lambda item: item["condition_id"])
    return data


def _snapshot_payload(snapshot: dict[str, Any]) -> tuple[str, str]:
    content_id = _digest("decision_snapshot_content", snapshot["payload"])
    snapshot_id = _digest("decision_snapshot", {"snapshot_type": snapshot["snapshot_type"], "reference_id": snapshot["reference_id"], "version": snapshot["version"], "content_id": content_id})
    return content_id, snapshot_id


def _node_payload(node: dict[str, Any]) -> dict[str, Any]:
    data = _without(node, "node_id", "content_id")
    data["input_content_ids"] = sorted(data.get("input_content_ids", []))
    data["output_content_ids"] = sorted(data.get("output_content_ids", []))
    data["diagnostics"] = sorted(data.get("diagnostics", []))
    return data


def _provenance_payload(provenance: dict[str, Any]) -> dict[str, Any]:
    data = _without(provenance, "provenance_id", "content_id", "runtime_metadata")
    if data.get("predecessor_hash_pointer") is None:
        data.pop("predecessor_hash_pointer", None)
    data["snapshot_ids"] = sorted(data.get("snapshot_ids", []))
    data["snapshots"] = sorted(data.get("snapshots", []), key=lambda item: (item["snapshot_type"], item["reference_id"]))
    data["execution_nodes"] = sorted(data.get("execution_nodes", []), key=lambda item: (item["sequence"], item["node_key"]))
    return data


def _evidence_observation_content(item: dict[str, Any]) -> str:
    payload = {
        "evidence_id": item["evidence_id"], "status": item["status"],
        "resolved_reference": item["resolved_reference"], "observed_result": item["observed_result"],
        "expected_result": item["expected_result"], "matches_expectation": item["matches_expectation"],
        "family": item.get("family"), "stages": item.get("stages", []), "verifier": item["verifier"],
        "diagnostics": item.get("diagnostics", []), "source_version": item["source_version"],
        "capability_ids": item.get("capability_ids", []),
    }
    return _digest("evidence_obs", payload, length=12)


def _validate_frozen_chain(
    case: dict[str, Any], policy: dict[str, Any], decision: dict[str, Any], provenance: dict[str, Any],
    catalog_by_id: dict[str, dict[str, Any]], package_payloads: dict[str, Any], manifest: dict[str, Any],
) -> tuple[list[str], dict[str, int | bool | str]]:
    errors: list[str] = []
    metrics: dict[str, int | bool | str] = {}
    snapshots = provenance.get("snapshots", [])
    by_type: dict[str, dict[str, Any]] = {}
    for snapshot in snapshots:
        content_id, snapshot_id = _snapshot_payload(snapshot)
        if snapshot.get("content_id") != content_id or snapshot.get("snapshot_id") != snapshot_id:
            errors.append(f"snapshot identity mismatch: {snapshot.get('snapshot_type')}")
        if snapshot.get("snapshot_type") in by_type:
            errors.append(f"duplicate snapshot type: {snapshot.get('snapshot_type')}")
        by_type[snapshot.get("snapshot_type")] = snapshot
    predecessor = case.get("predecessor_hash_pointer")
    expected_snapshot_types = set(EXPECTED_SNAPSHOT_TYPES)
    if predecessor is not None:
        expected_snapshot_types.add("audit_lineage")
    if set(by_type) != expected_snapshot_types:
        errors.append("frozen snapshot type set mismatch")
    if len(snapshots) != len(expected_snapshot_types):
        errors.append("frozen snapshot count mismatch")
    if errors:
        return errors, metrics
    if by_type["assurance_case"]["payload"] != case:
        errors.append("top-level assurance case differs from frozen snapshot")
    if by_type["review_policy"]["payload"] != policy:
        errors.append("top-level review policy differs from frozen snapshot")
    if decision.get("decision_provenance") != provenance:
        errors.append("top-level provenance differs from embedded decision provenance")
    if decision.get("predecessor_hash_pointer") != predecessor:
        errors.append("review decision predecessor pointer mismatch")
    if provenance.get("predecessor_hash_pointer") != predecessor:
        errors.append("review provenance predecessor pointer mismatch")
    if predecessor is not None:
        lineage = by_type["audit_lineage"]["payload"]
        if lineage.get("predecessor_hash_pointer") != predecessor:
            errors.append("frozen audit lineage predecessor pointer mismatch")
    if policy.get("policy_id") not in catalog_by_id or catalog_by_id.get(policy.get("policy_id")) != policy:
        errors.append("selected review policy differs from frozen policy catalog")
    rules_payload = by_type["rule_registry"]["payload"]
    capabilities_payload = by_type["capability_registry"]["payload"]
    evidence_payload = by_type["evidence_registry"]["payload"]
    resolution_payload = by_type["evidence_resolution"]["payload"]
    rules = rules_payload.get("rules", [])
    capabilities = capabilities_payload.get("capabilities", [])
    definitions = evidence_payload.get("definitions", [])
    observations = resolution_payload.get("observations", [])
    rule_ids = {str(item.get("id")) for item in rules}
    capability_ids = {str(item.get("capability_id")) for item in capabilities}
    evidence_ids = {str(item.get("evidence_id")) for item in definitions}
    observation_ids = {str(item.get("evidence_id")) for item in observations}
    metrics.update({
        "rule_snapshot_count": len(rules), "capability_snapshot_count": len(capabilities),
        "evidence_definition_count": len(definitions), "evidence_observation_count": len(observations),
        "assurance_claim_count": len(case.get("claims", [])),
        "selected_policy_check_count": len(policy.get("checks", [])),
    })
    if len(rules) != EXPECTED_RULE_COUNT or len(rule_ids) != EXPECTED_RULE_COUNT: errors.append("frozen rule registry count or uniqueness mismatch")
    if len(capabilities) != EXPECTED_CAPABILITY_COUNT or len(capability_ids) != EXPECTED_CAPABILITY_COUNT: errors.append("frozen capability registry count or uniqueness mismatch")
    if len(definitions) != EXPECTED_EVIDENCE_COUNT or len(evidence_ids) != EXPECTED_EVIDENCE_COUNT: errors.append("frozen evidence registry count or uniqueness mismatch")
    if len(observations) != EXPECTED_EVIDENCE_COUNT or observation_ids != evidence_ids: errors.append("frozen evidence observation matrix mismatch")
    for observation in observations:
        if observation.get("content_id") != _evidence_observation_content(observation):
            errors.append(f"evidence observation content ID mismatch: {observation.get('evidence_id')}")
    known_pack_ids = {str(item.get("pack_id")) for item in rules_payload.get("rule_sources", {}).values()}
    for definition in definitions:
        if set(definition.get("capability_ids", [])) - capability_ids: errors.append(f"evidence has unknown capability reference: {definition.get('evidence_id')}")
        if set(definition.get("rule_ids", [])) - rule_ids: errors.append(f"evidence has unknown rule reference: {definition.get('evidence_id')}")
        if set(definition.get("pack_ids", [])) - known_pack_ids: errors.append(f"evidence has unknown pack reference: {definition.get('evidence_id')}")
    errors.extend(_validate_assurance_case(case, capability_ids, evidence_ids, rule_ids))
    if set(decision.get("relevant_capability_ids", [])) - capability_ids: errors.append("review decision has unknown capability references")
    if set(decision.get("relevant_evidence_ids", [])) - evidence_ids: errors.append("review decision has unknown evidence references")
    if set(decision.get("relevant_rule_ids", [])) - rule_ids: errors.append("review decision has unknown rule references")
    if policy.get("content_id") != decision.get("policy_content_id"): errors.append("decision policy content reference mismatch")
    if case.get("content_id") != decision.get("assurance_case_content_id"): errors.append("decision assurance content reference mismatch")
    subject = _subject_type(case)
    if subject != policy.get("subject_type") or subject != decision.get("subject_type"): errors.append("review subject type mismatch")
    if case.get("cad_family") not in policy.get("applicable_families", []): errors.append("review policy family mismatch")
    if case.get("operation") not in policy.get("applicable_operations", []): errors.append("review policy operation mismatch")
    package_snapshot = by_type["audit_package_observation"]["payload"]
    package_result = package_snapshot.get("result") if package_snapshot.get("supplied") else None
    expected_findings = []
    expected_conditions = []
    for check in sorted(policy.get("checks", []), key=lambda item: item["check_id"]):
        try:
            finding = _finding(check, _evaluate_check(check, case, definitions, observations, package_result))
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"offline policy check failed: {check.get('check_id')}: {exc}")
            continue
        expected_findings.append(finding)
        condition = _condition(check, finding)
        if condition is not None: expected_conditions.append(condition)
    expected_findings.sort(key=lambda item: item["finding_id"])
    expected_conditions.sort(key=lambda item: item["condition_id"])
    if expected_findings != decision.get("findings", []): errors.append("offline policy finding replay mismatch")
    if expected_conditions != decision.get("conditions", []): errors.append("offline acceptance condition replay mismatch")
    status = _decision_status(policy, expected_findings)
    if decision.get("decision_status") != status: errors.append("offline decision precedence mismatch")
    expected_counts = {
        "passed_check_count": sum(item["status"] == "passed" for item in expected_findings),
        "failed_check_count": sum(item["status"] == "failed" for item in expected_findings),
        "unresolved_check_count": sum(item["status"] in {"unresolved", "not_checked"} for item in expected_findings),
        "not_applicable_check_count": sum(item["status"] == "not_applicable" for item in expected_findings),
        "blocking_finding_count": sum(item["status"] in {"failed", "unresolved", "not_checked"} and item["severity"] == "blocking" for item in expected_findings),
        "manual_review_finding_count": sum(item["status"] in {"failed", "unresolved", "not_checked"} and item["severity"] == "manual_review" for item in expected_findings),
        "conditional_finding_count": sum(item["status"] in {"failed", "unresolved", "not_checked"} and item["severity"] == "conditional" for item in expected_findings),
    }
    for key, expected in expected_counts.items():
        if decision.get(key) != expected: errors.append(f"review decision count mismatch: {key}")
    core_payload = _decision_payload({**decision, "decision_provenance": None})
    core_content = _digest("review_decision_core_content", core_payload)
    nodes = provenance.get("execution_nodes", [])
    node_by_key = {item.get("node_key"): item for item in nodes}
    if len(node_by_key) != len(nodes): errors.append("duplicate provenance execution node key")
    sequences = [item.get("sequence") for item in nodes]
    if sequences != list(range(len(nodes))): errors.append("provenance execution sequence mismatch")
    for node in nodes:
        payload = _node_payload(node)
        content = _digest("review_execution_node_content", payload)
        node_id = _digest("review_execution_node", {"node_key": node["node_key"], "sequence": node["sequence"], "content_id": content})
        if node.get("content_id") != content or node.get("node_id") != node_id: errors.append(f"execution node identity mismatch: {node.get('node_key')}")
    for check in policy.get("checks", []):
        node = node_by_key.get(f"check:{check['check_id']}")
        finding = next((item for item in expected_findings if item["check_id"] == check["check_id"]), None)
        if node is None or finding is None: errors.append(f"missing check execution node: {check['check_id']}")
        elif node.get("status") != finding["status"] or finding["content_id"] not in node.get("output_content_ids", []): errors.append(f"check execution node result mismatch: {check['check_id']}")
    precedence_node = node_by_key.get("deterministic_precedence_v1")
    if precedence_node is None or precedence_node.get("observed_value") != status or core_content not in precedence_node.get("output_content_ids", []): errors.append("decision precedence execution node mismatch")
    lineage_nodes = [item for item in nodes if item.get("node_type") == "lineage_binding"]
    if predecessor is None and lineage_nodes:
        errors.append("unexpected lineage binding node for genesis package")
    if predecessor is not None:
        if len(lineage_nodes) != 1 or lineage_nodes[0].get("observed_value", {}).get("predecessor_hash_pointer") != predecessor:
            errors.append("predecessor lineage binding execution node mismatch")
    registry_contract = {"registry_version": "1.0", "check_algorithms": {kind: "1.0" for kind in sorted(CHECK_TYPES)}}
    registry_id = _digest("review_check_registry", registry_contract)
    strategy_id = _digest("review_decision_strategy", DECISION_PRECEDENCE)
    if by_type["check_registry"]["payload"] != registry_contract or provenance.get("check_registry_content_id") != registry_id: errors.append("frozen check registry contract mismatch")
    if by_type["decision_strategy"]["payload"] != DECISION_PRECEDENCE or provenance.get("decision_strategy_content_id") != strategy_id: errors.append("frozen decision precedence contract mismatch")
    boundary_payload = by_type["boundary_conditions"]["payload"]
    if provenance.get("active_boundary_conditions") != boundary_payload: errors.append("active boundary condition snapshot mismatch")
    expected_snapshot_ids = [
        item["snapshot_id"]
        for item in sorted(snapshots, key=lambda item: (item["snapshot_type"], item["reference_id"]))
    ]
    if provenance.get("snapshot_ids") != expected_snapshot_ids: errors.append("provenance snapshot index mismatch")
    if provenance.get("policy_snapshot_id") != by_type["review_policy"]["snapshot_id"]: errors.append("provenance policy snapshot pointer mismatch")
    if provenance.get("assurance_case_snapshot_id") != by_type["assurance_case"]["snapshot_id"]: errors.append("provenance assurance snapshot pointer mismatch")
    if provenance.get("evidence_definition_count") != len(definitions) or provenance.get("evidence_observation_count") != len(observations): errors.append("provenance evidence count mismatch")
    provenance_content = _digest("decision_provenance_content", _provenance_payload(provenance))
    provenance_id = _digest("decision_provenance", {"content_id": provenance_content})
    if provenance.get("content_id") != provenance_content or provenance.get("provenance_id") != provenance_id: errors.append("decision provenance identity mismatch")
    decision_content = _digest("review_decision_content", _decision_payload(decision))
    if decision.get("content_id") != decision_content or decision.get("decision_id") != _digest("review_decision", {"content_id": decision_content}): errors.append("review decision identity mismatch")
    if package_payloads["capability_snapshot.json"] != {item: next(cap for cap in capabilities if cap["capability_id"] == item) for item in case.get("capability_references", [])}: errors.append("capability snapshot does not match frozen registry")
    if package_payloads["evidence_snapshot.json"] != {item: next(evd for evd in definitions if evd["evidence_id"] == item) for item in case.get("evidence_references", [])}: errors.append("evidence snapshot does not match frozen registry")
    if package_payloads["validation_summary.json"] != case.get("validation_observations", []): errors.append("validation summary differs from assurance case")
    if package_payloads["artifact_manifest.json"] != case.get("artifact_records", []): errors.append("artifact manifest differs from assurance case")
    if package_payloads["intent.json"] != (case.get("structured_intent") or case.get("input_request")): errors.append("intent snapshot differs from assurance case")
    if manifest.get("review_policy_catalog_policy_count") != EXPECTED_POLICY_COUNT or manifest.get("review_policy_catalog_check_count") != EXPECTED_POLICY_CHECK_COUNT: errors.append("manifest policy catalog counts mismatch")
    if manifest.get("review_policy_catalog_content_id") != _digest("review_policy_catalog", package_payloads["review_policy_catalog_snapshot.json"]): errors.append("manifest policy catalog identity mismatch")
    metrics.update({
        "policy_catalog_count": len(catalog_by_id), "policy_catalog_check_count": sum(len(item["checks"]) for item in catalog_by_id.values()),
        "execution_node_count": len(nodes), "finding_count": len(expected_findings), "condition_count": len(expected_conditions),
        "static_check_replay_count": len(expected_findings), "static_check_replay_mismatch_count": sum("replay mismatch" in item for item in errors),
        "decision_precedence_verified": decision.get("decision_status") == status,
        "frozen_registry_validation_passed": not any("registry" in item or "reference" in item for item in errors),
    })
    return errors, metrics


def _validate_cas_envelope(
    envelope: dict[str, Any],
    *,
    files: dict[str, bytes],
    manifest: dict[str, Any],
    case: dict[str, Any],
    decision: dict[str, Any],
    provenance: dict[str, Any],
) -> tuple[list[str], dict[str, int | bool | str]]:
    errors: list[str] = []
    allowed_keys = {
        "schema_version", "hash_algorithm", "content_address", "predecessor_hash_pointer",
        "assurance_case_id", "review_decision_id", "cad_family", "operation", "tool_version", "objects",
    }
    if set(envelope) != allowed_keys:
        errors.append("CAS envelope field set mismatch")
    if envelope.get("schema_version") != "1.0" or envelope.get("hash_algorithm") != "sha256":
        errors.append("unsupported CAS envelope contract")
    predecessor = envelope.get("predecessor_hash_pointer")
    if predecessor is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", str(predecessor)):
        errors.append("CAS predecessor content address is malformed")
    objects = envelope.get("objects")
    if not isinstance(objects, list):
        return errors + ["CAS envelope objects must be a list"], {"cas_object_count": 0}
    paths = [item.get("logical_path") for item in objects if isinstance(item, dict)]
    if len(paths) != len(objects) or len(paths) != len(set(paths)):
        errors.append("CAS object paths are missing or duplicated")
    if objects != sorted(objects, key=lambda item: item.get("logical_path", "")):
        errors.append("CAS object order is not deterministic")
    expected_paths = set(files) - {"manifest.json", "checksums.json", CAS_ENVELOPE_FILE}
    if set(paths) != expected_paths:
        errors.append("CAS object inventory does not match structural package files")
    object_hash_mismatches = 0
    for item in objects:
        path = str(item.get("logical_path", ""))
        if not _safe_name(path) or path not in files:
            errors.append(f"unsafe or missing CAS object path: {path}")
            continue
        expected = "sha256:" + _sha256(files[path])
        if item.get("content_address") != expected:
            object_hash_mismatches += 1
            errors.append(f"CAS object content address mismatch: {path}")
    deterministic = dict(envelope)
    deterministic.pop("content_address", None)
    expected_address = "sha256:" + hashlib.sha256(
        json.dumps(deterministic, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    if envelope.get("content_address") != expected_address:
        errors.append("CAS envelope content address mismatch")
    for key, expected in (
        ("assurance_case_id", case.get("assurance_case_id")),
        ("review_decision_id", decision.get("decision_id")),
        ("cad_family", case.get("cad_family")),
        ("operation", case.get("operation")),
    ):
        if envelope.get(key) != expected:
            errors.append(f"CAS envelope {key} mismatch")
    if predecessor != case.get("predecessor_hash_pointer"):
        errors.append("CAS predecessor does not match assurance case")
    if predecessor != decision.get("predecessor_hash_pointer"):
        errors.append("CAS predecessor does not match review decision")
    if predecessor != provenance.get("predecessor_hash_pointer"):
        errors.append("CAS predecessor does not match review provenance")
    if manifest.get("package_id") != expected_address or manifest.get("package_content_address") != expected_address:
        errors.append("manifest primary package ID does not match CAS content address")
    if manifest.get("predecessor_hash_pointer") != predecessor:
        errors.append("manifest predecessor pointer mismatch")
    if manifest.get("cas_envelope_schema_version") != envelope.get("schema_version"):
        errors.append("manifest CAS envelope version mismatch")
    if manifest.get("cas_object_count") != len(objects):
        errors.append("manifest CAS object count mismatch")
    return errors, {
        "cas_object_count": len(objects),
        "cas_object_hash_mismatch_count": object_hash_mismatches,
        "cas_content_address_verified": envelope.get("content_address") == expected_address,
        "predecessor_pointer_present": predecessor is not None,
    }


def verify_offline_audit_package(package_path: str | os.PathLike[str]) -> OfflineVerificationResult:
    """Fail-fast static verification using only files enclosed by the package."""

    root = Path(package_path)
    base_metrics: dict[str, int | bool | str] = {
        "hash_mismatch_count": 0, "canonical_json_mismatch_count": 0,
        "portability_violation_count": 0, "unsafe_path_count": 0,
        "offline_registry_access_count": 0, "network_access_count": 0,
    }
    if not root.is_dir():
        return _result(errors=["audit package directory does not exist"], stage="package_structure", metrics=base_metrics)
    errors: list[str] = []
    files: dict[str, bytes] = {}
    try:
        entries = sorted(os.scandir(root), key=lambda item: item.name)
    except OSError as exc:
        return _result(errors=[f"could not inspect audit package: {exc}"], stage="package_structure", metrics=base_metrics)
    for entry in entries:
        if entry.is_symlink():
            errors.append(f"symbolic links are not allowed: {entry.name}")
            continue
        if not entry.is_file(follow_symlinks=False):
            errors.append(f"nested or non-file package entry is not allowed: {entry.name}")
            continue
        if not _safe_name(entry.name):
            base_metrics["unsafe_path_count"] = int(base_metrics["unsafe_path_count"]) + 1
            errors.append(f"unsafe package entry name: {entry.name}")
            continue
        try:
            data = Path(entry.path).read_bytes()
        except OSError as exc:
            errors.append(f"could not read package entry {entry.name}: {exc}")
            continue
        if len(data) > 25 * 1024 * 1024:
            errors.append(f"package entry exceeds static verifier size limit: {entry.name}")
            continue
        files[entry.name] = data
    missing = sorted(REQUIRED_FILES - set(files))
    if missing: errors.append("missing required files: " + ", ".join(missing))
    if errors:
        return _result(errors=errors, stage="package_structure", metrics=base_metrics)
    try:
        checksums = _load_json_bytes(files["checksums.json"], "checksums.json")
        manifest = _load_json_bytes(files["manifest.json"], "manifest.json")
    except ValueError as exc:
        return _result(errors=[str(exc)], stage="checksum_manifest", metrics=base_metrics)
    if not isinstance(checksums, dict) or not isinstance(manifest, dict):
        return _result(errors=["manifest and checksums must contain JSON objects"], stage="checksum_manifest", metrics=base_metrics)
    package_schema = manifest.get("schema_version")
    if package_schema == "1.2" and CAS_ENVELOPE_FILE not in files:
        return _result(
            errors=["missing required files: cas_envelope.json"],
            stage="package_structure",
            manifest=manifest,
            metrics=base_metrics,
        )
    expected_checksum_names = set(files) - {"checksums.json"}
    if set(checksums) != expected_checksum_names:
        errors.append("checksum inventory does not exactly match enclosed files")
    for name in sorted(expected_checksum_names):
        if checksums.get(name) != _sha256(files[name]):
            errors.append(f"checksum mismatch: {name}")
            base_metrics["hash_mismatch_count"] = int(base_metrics["hash_mismatch_count"]) + 1
    inventory = manifest.get("file_inventory")
    expected_inventory_names = set(files) - {"manifest.json", "checksums.json"}
    if not isinstance(inventory, dict) or set(inventory) != expected_inventory_names:
        errors.append("logical file inventory does not exactly match enclosed payloads")
    else:
        for name in sorted(expected_inventory_names):
            if inventory.get(name) != _sha256(files[name]):
                errors.append(f"logical inventory mismatch: {name}")
                base_metrics["hash_mismatch_count"] = int(base_metrics["hash_mismatch_count"]) + 1
    if errors:
        return _result(errors=errors, stage="checksum_manifest", manifest=manifest, metrics=base_metrics)
    payloads: dict[str, Any] = {"manifest.json": manifest, "checksums.json": checksums}
    for name in sorted((JSON_FILES.intersection(files)) - {"manifest.json", "checksums.json"}):
        try:
            payloads[name] = _load_json_bytes(files[name], name)
        except ValueError as exc:
            errors.append(str(exc))
    for name in sorted(JSON_FILES):
        if name in payloads and files[name] != _canonical_json_bytes(payloads[name]):
            errors.append(f"non-canonical JSON serialization: {name}")
            base_metrics["canonical_json_mismatch_count"] = int(base_metrics["canonical_json_mismatch_count"]) + 1
    for name in ("assurance_case.md", "review_decision.md"):
        try:
            files[name].decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"invalid UTF-8 Markdown: {name}")
        if b"\r" in files[name]: errors.append(f"platform-specific Markdown line ending: {name}")
    if errors:
        return _result(errors=errors, stage="canonical_serialization", manifest=manifest, metrics=base_metrics)
    for name in sorted(payloads):
        violations = _portability_errors(payloads[name], name)
        base_metrics["portability_violation_count"] = int(base_metrics["portability_violation_count"]) + len(violations)
        errors.extend(violations)
    if package_schema not in SUPPORTED_PACKAGE_SCHEMAS:
        errors.append(f"unsupported audit package schema: {manifest.get('schema_version')}")
    if manifest.get("portability_profile") != "intentforge_portable_audit_v1" or manifest.get("canonical_json") is not True:
        errors.append("portable audit profile metadata is missing or unsupported")
    case = payloads["assurance_case.json"]
    decision = payloads["review_decision.json"]
    provenance = payloads["review_decision_provenance.json"]
    if case.get("request_id") != "portable_request": errors.append("assurance request ID was not normalized")
    if case.get("run_id") not in {None, "portable_run"}: errors.append("assurance run ID was not normalized")
    if case.get("parent_run_id") not in {None, "portable_parent_run"}: errors.append("assurance parent run ID was not normalized")
    if errors:
        return _result(errors=errors, stage="portability", manifest=manifest, decision=decision, metrics=base_metrics)
    expected_package_id = None
    if package_schema == "1.1":
        expected_package_id = _digest("audit_package", {"assurance_case_id": case.get("assurance_case_id"), "files": dict(sorted(inventory.items()))})
        if manifest.get("package_id") != expected_package_id: errors.append("audit package logical content ID mismatch")
    if manifest.get("assurance_case_id") != case.get("assurance_case_id"): errors.append("manifest assurance case ID mismatch")
    catalog_errors, catalog_by_id = _validate_policy_catalog(payloads["review_policy_catalog_snapshot.json"])
    errors.extend(catalog_errors)
    chain_errors, chain_metrics = _validate_frozen_chain(
        case, payloads["review_policy_snapshot.json"], decision, provenance,
        catalog_by_id, payloads, manifest,
    )
    errors.extend(chain_errors)
    base_metrics.update(chain_metrics)
    if package_schema == "1.2":
        cas_errors, cas_metrics = _validate_cas_envelope(
            payloads[CAS_ENVELOPE_FILE],
            files=files,
            manifest=manifest,
            case=case,
            decision=decision,
            provenance=provenance,
        )
        errors.extend(cas_errors)
        base_metrics.update(cas_metrics)
        expected_package_id = payloads[CAS_ENVELOPE_FILE].get("content_address")
    base_metrics.update({
        "file_count": len(files), "deterministic_package_id_verified": manifest.get("package_id") == expected_package_id,
        "offline_static_chain_verified": not chain_errors,
    })
    return _result(
        errors=errors,
        stage="static_chain" if errors else None,
        manifest=manifest,
        decision=decision,
        metrics=base_metrics,
        warnings=[
            "Offline verification validates the frozen static chain; it does not re-run CAD generation, simulation, or network checks."
        ],
    )
