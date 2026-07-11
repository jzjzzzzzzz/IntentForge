"""Build deterministic assurance cases from existing IntentForge workflow results."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from intentforge.assurance.claims import make_claim
from intentforge.assurance.schema import (
    ArtifactRecord, AssuranceCase, LimitationRecord, ValidationObservation, canonical_digest,
)
from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.evaluator import evaluate_parameter_table
from intentforge.knowledge.evidence_bundles import build_all_evidence_bundles
from intentforge.knowledge.evidence_registry import load_evidence_definitions
from intentforge.knowledge.report import make_knowledge_report
from intentforge.knowledge.reasoning.engine import build_engineering_reasoning_report
from intentforge.knowledge.rules import RuleRegistry
from intentforge.schemas import FeaturePlan, ParameterTable
from intentforge.workflows import parse_build_workflow, parse_prompt_workflow

DEFAULT_PROMPTS = {
    "wall_mounted_bracket": "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
    "l_bracket": "Make an L-bracket 80 mm wide with 60 mm legs, 8 mm thick, and two holes on each leg.",
}


class AssuranceBuildError(ValueError):
    pass


def _file_hash(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest(), path.stat().st_size


def _safe_artifact_path(raw: str) -> str | None:
    normalized = raw.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if "output" in parts:
        return PurePosixPath(*parts[parts.index("output"):]).as_posix()
    if not PurePosixPath(normalized).is_absolute() and ".." not in parts:
        return normalized
    return None


def _artifacts(result: dict[str, Any], family: str) -> list[ArtifactRecord]:
    records: list[ArtifactRecord] = []
    seen: set[tuple[str, str]] = set()
    for artifact in result.get("artifacts", []) or []:
        if not isinstance(artifact, dict) or not artifact.get("path"):
            continue
        safe_path = _safe_artifact_path(str(artifact["path"]))
        if safe_path is None and artifact.get("persistent") is False:
            safe_path = (PurePosixPath("output") / Path(str(artifact["path"])).name).as_posix()
        if safe_path is None:
            continue
        path_parts = PurePosixPath(safe_path).parts
        if "parsed_runs" in path_parts or "edit_parse_runs" in path_parts:
            continue
        kind = str(artifact.get("kind", "artifact"))
        key = (kind, safe_path)
        if key in seen:
            continue
        seen.add(key)
        source = Path(str(artifact["path"]))
        content_hash = size = None
        if source.exists() and source.is_file():
            content_hash, size = _file_hash(source)
        logical_identity = {"kind": kind, "path": safe_path}
        integrity_identity = {**logical_identity, "hash": content_hash, "size": size}
        artifact_id = canonical_digest("artifact", logical_identity)
        records.append(ArtifactRecord(
            artifact_id=artifact_id, artifact_type=kind, logical_name=Path(safe_path).name,
            path=safe_path, content_hash=content_hash, size=size,
            producer_operation=str(result.get("operation", "unknown")), family=family,
            request_id=result.get("request_id"), run_id=result.get("run_id"),
            validation_status="verified" if content_hash else "not_checked",
            metadata_id=canonical_digest("artifact_meta", integrity_identity),
        ))
    return sorted(records, key=lambda item: item.artifact_id)


def _validation_observations(result: dict[str, Any], family: str, artifacts: list[ArtifactRecord]) -> list[ValidationObservation]:
    report = result.get("validation_report") or {}
    if not isinstance(report, dict):
        return []
    artifact_ids = [item.artifact_id for item in artifacts]
    observations: list[ValidationObservation] = []
    if report:
        passed = bool(report.get("valid"))
        payload = {"type": "geometry_validation", "passed": passed, "checks": report.get("checks", [])}
        observations.append(ValidationObservation(
            validation_id=canonical_digest("validation", payload), validation_type="geometry_validation",
            status="passed" if passed else "failed", observed_result={"valid": passed, "checks": len(report.get("checks", []))},
            expected_result={"valid": True}, diagnostics=[report.get("summary", "")], family=family,
            stages=["geometry_validation"], artifact_ids=artifact_ids, content_id=canonical_digest("validation_content", payload),
        ))
    metadata = report.get("metadata", {}) if isinstance(report, dict) else {}
    for key, stage, validation_type in (
        ("topology", "topology_inspection", "topology_inspection"),
        ("feature_recognition", "feature_recognition", "feature_recognition"),
    ):
        value = metadata.get(key)
        if not isinstance(value, dict):
            continue
        ok = value.get("passed", value.get("is_valid", True)) is not False
        payload = {"type": validation_type, "value": value}
        observations.append(ValidationObservation(
            validation_id=canonical_digest("validation", payload), validation_type=validation_type,
            status="passed" if ok else "warning", observed_result=value, expected_result={"passed": True},
            diagnostics=list(value.get("warnings", []) or []), family=family, stages=[stage],
            artifact_ids=artifact_ids, content_id=canonical_digest("validation_content", payload),
        ))
    return sorted(observations, key=lambda item: item.validation_type)


def _capabilities(family: str, profile: str, rejected: bool) -> tuple[list[Any], list[Any]]:
    all_caps = [item for item in load_capability_manifest().capabilities if item.family == family]
    if rejected:
        exercised = [item for item in all_caps if item.status == "unsupported"]
    else:
        allowed_stages = {"parsing", "intent_schema", "knowledge", "constraint_compilation"}
        if profile in {"standard", "full"}:
            allowed_stages.update({"cad_generation", "geometry_validation", "topology_inspection", "feature_recognition", "engineering_reasoning"})
        exercised = [item for item in all_caps if item.status != "unsupported" and set(item.stages).intersection(allowed_stages)]
    limitations = [item for item in all_caps if item.status in {"partially_supported", "unsupported"}]
    return sorted(exercised, key=lambda item: item.capability_id), sorted(limitations, key=lambda item: item.capability_id)


def build_assurance_case(result: dict[str, Any], *, profile: str = "standard", input_request: str | None = None) -> AssuranceCase:
    """Adapt one existing workflow result into a scoped assurance case."""

    if profile not in {"static", "standard", "full"}:
        raise AssuranceBuildError(f"unsupported assurance profile: {profile}")
    family = result.get("object_type") or (result.get("intent") or {}).get("family")
    if family not in DEFAULT_PROMPTS:
        raise AssuranceBuildError("assurance input is missing a supported CAD family")
    rejected = not bool(result.get("ok")) and not bool(result.get("validation_report"))
    exercised, boundary_caps = _capabilities(family, profile, rejected)
    capability_ids = [item.capability_id for item in exercised]
    definitions = load_evidence_definitions()
    evidence_ids = sorted({d.evidence_id for d in definitions if set(d.capability_ids).intersection(capability_ids)})
    bundles = build_all_evidence_bundles(family=family, runtime=False)
    bundle_ids = {b.capability_id: b.bundle_id for b in bundles if b.capability_id in capability_ids}

    parameter_data = result.get("parameters")
    if not parameter_data and isinstance(result.get("edit_report"), dict):
        parameter_data = (result["edit_report"].get("metadata") or {}).get("updated_parameter_table")
    feature_plan_data = result.get("feature_plan")
    rule_registry = RuleRegistry.load()
    rules = rule_registry.for_family(family)
    sources = rule_registry.rule_sources()
    rule_refs: list[dict[str, Any]] = []
    reasoning_summary = None
    if parameter_data:
        table = ParameterTable.model_validate(parameter_data)
        plan = FeaturePlan.model_validate(feature_plan_data) if feature_plan_data else None
        findings = evaluate_parameter_table(table, plan)
        finding_by_id = {f.rule_id: f for f in findings}
        knowledge_report = make_knowledge_report(findings, rules_checked=len(rules), timestamp="deterministic")
        reasoning = build_engineering_reasoning_report(
            model_family=family, knowledge_report=knowledge_report, parameters={p.name: p.value for p in table.parameters}, timestamp="deterministic",
        )
        reasoning_summary = reasoning.model_dump(mode="json")
        for rule in rules:
            finding = finding_by_id.get(rule.id)
            source = sources.get(rule.id, {})
            rule_refs.append({
                "rule_id": rule.id, "rule_version": rule.rule_version, "pack_id": source.get("pack_id"),
                "pack_version": source.get("pack_version"), "applicability": "applicable" if finding else "not_applicable",
                "outcome": "passed" if finding and finding.passed else "warning" if finding else "not_applicable",
                "affected_parameters": sorted(rule.reasoning.get("affects", [])), "provenance": rule.source_reference,
            })
    else:
        rule_refs = [{"rule_id": r.id, "rule_version": r.rule_version, "pack_id": sources.get(r.id, {}).get("pack_id"),
                      "pack_version": sources.get(r.id, {}).get("pack_version"), "applicability": "not_evaluated",
                      "outcome": "not_evaluated", "affected_parameters": [], "provenance": r.source_reference} for r in rules]

    constraints = []
    for item in (result.get("constraints") or {}).get("constraints", []):
        constraints.append({"constraint_id": item.get("id"), "constraint_type": item.get("kind"),
                            "expression": item.get("expression"), "affected_parameters": item.get("parameters", []),
                            "compile_status": "compiled", "validation_status": "not_checked"})
    artifacts = _artifacts(result, family)
    observations = _validation_observations(result, family, artifacts) if profile != "static" else []
    limitations: list[LimitationRecord] = []
    for cap in boundary_caps:
        for index, text in enumerate(cap.limitations or [cap.rejection_behavior]):
            if not text:
                continue
            payload = {"capability": cap.capability_id, "text": text, "index": index}
            limitations.append(LimitationRecord(
                limitation_id=canonical_digest("limitation", payload), title=cap.title, description=text,
                family=family, capability_ids=[cap.capability_id], stages=cap.stages,
                significance="partial_support" if cap.status == "partially_supported" else "unsupported_boundary",
                review_required=True, source=f"capability:{cap.capability_id}", content_id=canonical_digest("limitation_content", payload),
            ))

    claims = []
    arguments = []
    def add(kind: str, **kwargs: Any) -> None:
        claim, argument = make_claim(kind, family=family, **kwargs)
        claims.append(claim); arguments.append(argument)

    cap_ev = {"capability_ids": capability_ids, "evidence_ids": evidence_ids}
    if rejected:
        add("unsupported_behavior_rejected", stages=["rejection"], **cap_ev)
        add("limitation_disclosed", status="partially_supported", stages=["rejection"], limitations=[x.description for x in limitations], required_review=True)
    else:
        add("request_interpreted", stages=["parsing"], **cap_ev)
        add("intent_schema_valid", stages=["intent_schema"], **cap_ev)
        add("family_supported", stages=["intent_schema"], **cap_ev)
        if result.get("feature_plan"):
            add("feature_plan_supported", stages=["intent_schema"], **cap_ev)
        if constraints:
            add("constraints_compiled", stages=["constraint_compilation"], **cap_ev)
        if parameter_data:
            add("engineering_rules_evaluated", stages=["knowledge"], rule_ids=[r.id for r in rules], **cap_ev)
        if profile != "static":
            if result.get("cad_exported"):
                add("geometry_generated", stages=["cad_generation"], artifact_ids=[a.artifact_id for a in artifacts], **cap_ev)
            geometry = [o for o in observations if o.validation_type == "geometry_validation"]
            if geometry:
                add("geometry_valid", status="supported" if geometry[0].status == "passed" else "failed", stages=["geometry_validation"], validation_ids=[geometry[0].validation_id], **cap_ev)
            topology = [o for o in observations if o.validation_type == "topology_inspection"]
            if topology: add("topology_inspected", stages=["topology_inspection"], validation_ids=[topology[0].validation_id], **cap_ev)
            recognition = [o for o in observations if o.validation_type == "feature_recognition"]
            if recognition: add("features_recognized", status="supported" if recognition[0].status == "passed" else "partially_supported", stages=["feature_recognition"], validation_ids=[recognition[0].validation_id], **cap_ev)
            if reasoning_summary: add("engineering_reasoning_completed", stages=["engineering_reasoning"], rule_ids=[r.id for r in rules], **cap_ev)
            if result.get("operation") == "edit_parse_apply" and result.get("accepted"):
                add("requested_edit_preserved_intent", stages=["intent_schema", "geometry_validation"], **cap_ev)
        add("capability_evidence_available", stages=["golden_verification"], **cap_ev)
        if profile == "full" and artifacts and all(a.content_hash for a in artifacts):
            add("artifact_integrity_verified", stages=["geometry_validation"], artifact_ids=[a.artifact_id for a in artifacts], **cap_ev)
        if limitations:
            add("limitation_disclosed", status="partially_supported", stages=["feature_recognition"], limitations=[x.description for x in limitations], required_review=True)

    failed = any(c.status == "failed" for c in claims)
    unresolved = any(c.status == "unresolved" for c in claims)
    overall = "assurance_failed" if failed else "assurance_unresolved" if unresolved else "assurance_complete_with_limitations" if limitations or rejected else "assurance_complete"
    request_id = str(result.get("request_id") or canonical_digest("request", {"input": input_request or ""}))
    request_summary: dict[str, Any] = {
        "summary": input_request or (result.get("intent") or {}).get("user_prompt"),
        "rejected": rejected,
        "error": result.get("error"),
    }
    edit_report = result.get("edit_report") if isinstance(result.get("edit_report"), dict) else {}
    if result.get("operation") in {"edit_parse", "edit_parse_apply"}:
        request_summary["edit_request"] = result.get("edit_request")
        request_summary["edit_trace"] = {
            "changed_parameters": sorted(
                str(item.get("parameter"))
                for item in edit_report.get("changed_parameters", [])
                if isinstance(item, dict) and item.get("parameter")
            ),
            "preserved_parameters": sorted(
                str(item.get("parameter"))
                for item in edit_report.get("preserved_parameters", [])
                if isinstance(item, dict) and item.get("parameter")
            ),
            "changes_applied": sorted(str(item) for item in edit_report.get("changes_applied", [])),
        }
    case_data = dict(
        assurance_case_id="pending", profile=profile, operation=str(result.get("operation", "parse_build")),
        request_id=request_id, run_id=result.get("run_id"),
        parent_run_id=result.get("parent_run_id") or edit_report.get("target_model_id"),
        input_request=request_summary, structured_intent=result.get("intent"), cad_family=family,
        feature_plan_summary=result.get("feature_plan") or {}, compiled_constraint_summary=sorted(constraints, key=lambda x: str(x.get("constraint_id"))),
        rule_references=sorted(rule_refs, key=lambda x: x["rule_id"]), capability_references=capability_ids,
        evidence_references=evidence_ids, claims=sorted(claims, key=lambda x: x.claim_id), arguments=sorted(arguments, key=lambda x: x.argument_id),
        validation_observations=observations, artifact_records=artifacts, limitations=sorted(limitations, key=lambda x: x.limitation_id),
        review_requirements=["External engineering review is required for load-specific, manufacturing, regulatory, or safety decisions."],
        reproducibility_metadata={"schema_version": "1.0", "capability_bundle_ids": bundle_ids, "deterministic": True},
        reasoning_summary=reasoning_summary, runtime_metadata={}, content_id="pending", overall_assurance_status=overall,
    )
    provisional = AssuranceCase.model_validate(case_data)
    content_id = canonical_digest("assurance_content", provisional.deterministic_payload())
    return provisional.model_copy(update={"assurance_case_id": canonical_digest("assurance_case", {"content_id": content_id}), "content_id": content_id})


def build_assurance_from_prompt(
    prompt: str | None = None, *, family: str = "wall_mounted_bracket", profile: str = "standard",
    dry_run: bool = False, output_root: str | Path | None = None, request_id: str | None = None,
) -> AssuranceCase:
    """Run the existing parse or parse-build workflow and adapt its result."""

    if family not in DEFAULT_PROMPTS:
        raise AssuranceBuildError(f"unsupported CAD family: {family}")
    text = prompt or DEFAULT_PROMPTS[family]
    if profile == "static":
        result = parse_prompt_workflow(text, output_root, write_outputs=False, request_id=request_id)
    else:
        result = parse_build_workflow(text, output_root, request_id=request_id, dry_run=dry_run)
    if not result.get("object_type") and not result.get("ok"):
        result["object_type"] = family
    return build_assurance_case(result, profile=profile, input_request=text)
