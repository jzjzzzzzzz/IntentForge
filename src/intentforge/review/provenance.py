"""Frozen review-decision provenance and deterministic replay verification."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from intentforge.assurance.schema import AssuranceCase, canonical_digest
from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.evidence_registry import load_evidence_definitions
from intentforge.knowledge.evidence_resolver import resolve_evidence
from intentforge.knowledge.evidence_schema import EvidenceDefinition, make_observation
from intentforge.knowledge.rules import RuleRegistry
from intentforge.review.provenance_schema import (
    DecisionProvenance,
    DecisionProvenanceVerification,
    FrozenDecisionSnapshot,
    REVIEW_CHECK_REGISTRY_VERSION,
    REVIEW_EVALUATOR_VERSION,
    REVIEW_PROVENANCE_SCHEMA_VERSION,
    ReviewExecutionNode,
)
from intentforge.review.schema import AcceptanceCondition, PolicyFinding, ReviewDecision, ReviewPolicy


DECISION_PRECEDENCE_CONTRACT = {
    "strategy": "deterministic_precedence_v1",
    "ordered_rules": [
        "required_blocking_unresolved_to_unresolved",
        "blocking_failed_to_rejected_by_policy",
        "manual_review_finding_to_manual_review_required",
        "conditional_finding_to_accepted_with_conditions",
        "all_required_checks_passed_to_accepted_within_declared_scope",
    ],
}

_PACKAGE_FIELDS = {
    "passed",
    "errors",
    "warnings",
    "package_id",
    "assurance_case_id",
    "file_count",
    "hash_mismatch_count",
    "review_decision_attached",
    "review_decision_validation_passed",
    "validation",
}


def _tool_version() -> str:
    try:
        return version("intentforge")
    except PackageNotFoundError:
        return "source-checkout"


def _stable_package_result(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {"supplied": False}

    def normalize(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                str(key): normalize(child)
                for key, child in sorted(item.items())
                if str(key) in _PACKAGE_FIELDS
            }
        if isinstance(item, list):
            normalized = [normalize(child) for child in item]
            return sorted(normalized, key=lambda child: str(child))
        if isinstance(item, tuple):
            return normalize(list(item))
        return item

    return {"supplied": True, "result": normalize(value)}


def check_registry_contract() -> dict[str, Any]:
    """Return the non-executable closed registry contract used for identity."""

    from intentforge.review.checks import CHECK_ALGORITHM_VERSIONS

    return {
        "registry_version": REVIEW_CHECK_REGISTRY_VERSION,
        "check_algorithms": {
            check_type: CHECK_ALGORITHM_VERSIONS[check_type]
            for check_type in sorted(CHECK_ALGORITHM_VERSIONS)
        },
    }


def check_registry_content_id() -> str:
    return canonical_digest("review_check_registry", check_registry_contract())


def decision_strategy_content_id() -> str:
    return canonical_digest("review_decision_strategy", DECISION_PRECEDENCE_CONTRACT)


@dataclass(frozen=True)
class ReviewEvaluationResources:
    """Isolated deterministic registries consumed by one evaluation."""

    rules: tuple[dict[str, Any], ...]
    rule_sources: dict[str, dict[str, str]]
    capability_manifest: dict[str, Any]
    evidence_definitions: tuple[dict[str, Any], ...]
    evidence_observations: tuple[dict[str, Any], ...]
    tool_version: str

    def check_context(self, package_result: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "__review_context__": True,
            "package_result": package_result,
            "evidence_definitions": list(self.evidence_definitions),
            "evidence_observations": list(self.evidence_observations),
        }


def collect_review_evaluation_resources(
    *,
    active_evidence_ids: set[str] | None = None,
) -> ReviewEvaluationResources:
    """Resolve all deterministic registries once for an isolated evaluation."""

    rule_registry = RuleRegistry.load()
    evidence_definitions = sorted(load_evidence_definitions(), key=lambda item: item.evidence_id)
    selected_ids = set(active_evidence_ids) if active_evidence_ids is not None else {
        item.evidence_id for item in evidence_definitions
    }
    selected_definitions = [item for item in evidence_definitions if item.evidence_id in selected_ids]
    evidence_report = resolve_evidence(selected_definitions, runtime=False)
    resolved = {item.evidence_id: item for item in evidence_report.observations}
    evidence_observations = sorted(
        [
            resolved.get(item.evidence_id)
            or make_observation(
                item,
                status="not_checked",
                observed_result="not selected for this review decision",
                matches_expectation=False,
                verifier="review_provenance_matrix",
                diagnostics=["evidence definition retained for complete matrix traceability"],
            )
            for item in evidence_definitions
        ],
        key=lambda item: item.evidence_id,
    )
    capabilities = load_capability_manifest()
    return ReviewEvaluationResources(
        rules=tuple(
            item.model_dump(mode="json")
            for item in sorted(rule_registry.rules, key=lambda rule: rule.id)
        ),
        rule_sources={key: rule_registry.rule_sources()[key] for key in sorted(rule_registry.rule_sources())},
        capability_manifest=capabilities.model_dump(mode="json"),
        evidence_definitions=tuple(item.model_dump(mode="json") for item in evidence_definitions),
        evidence_observations=tuple(
            {**item.deterministic_payload(), "content_id": item.content_id}
            for item in evidence_observations
        ),
        tool_version=_tool_version(),
    )


def _snapshot(snapshot_type: str, reference_id: str, version_value: str, payload: Any) -> FrozenDecisionSnapshot:
    return FrozenDecisionSnapshot(
        snapshot_type=snapshot_type,
        reference_id=reference_id,
        version=version_value,
        payload=payload,
    )


def _boundary_conditions(case: AssuranceCase, subject_type: str) -> dict[str, Any]:
    return {
        "subject_type": subject_type,
        "cad_family": case.cad_family,
        "operation": case.operation,
        "assurance_profile": case.profile,
        "overall_assurance_status": case.overall_assurance_status,
        "claim_statuses": {
            item.claim_id: {"claim_type": item.claim_type, "status": item.status}
            for item in sorted(case.claims, key=lambda claim: claim.claim_id)
        },
        "validation_statuses": {
            item.validation_id: {"validation_type": item.validation_type, "status": item.status}
            for item in sorted(case.validation_observations, key=lambda observation: observation.validation_id)
        },
        "limitations": {
            item.limitation_id: {
                "significance": item.significance,
                "review_required": item.review_required,
                "capability_ids": sorted(item.capability_ids),
                "rule_ids": sorted(item.rule_ids),
            }
            for item in sorted(case.limitations, key=lambda limitation: limitation.limitation_id)
        },
        "artifacts": {
            item.artifact_id: {
                "artifact_type": item.artifact_type,
                "content_hash": item.content_hash,
                "validation_status": item.validation_status,
            }
            for item in sorted(case.artifact_records, key=lambda artifact: artifact.artifact_id)
        },
        "review_requirements": sorted(case.review_requirements),
    }


def _registry_versions(resources: ReviewEvaluationResources) -> tuple[str, str]:
    capability_version = str(resources.capability_manifest.get("manifest_version", "1.0"))
    evidence_versions = sorted({str(item.get("version", "1.0")) for item in resources.evidence_definitions})
    evidence_version = "+".join(evidence_versions) if evidence_versions else "1.0"
    return capability_version, evidence_version


def build_decision_provenance(
    *,
    policy: ReviewPolicy,
    assurance_case: AssuranceCase,
    subject_type: str,
    package_result: dict[str, Any] | None,
    resources: ReviewEvaluationResources,
    findings: list[PolicyFinding],
    conditions: list[AcceptanceCondition],
    decision_status: str,
    decision_core_content_id: str,
    runtime_metadata: dict[str, Any] | None = None,
) -> DecisionProvenance:
    """Freeze all deterministic evaluation inputs and the ordered execution graph."""

    capability_version, evidence_version = _registry_versions(resources)
    policy_snapshot = _snapshot(
        "review_policy",
        policy.policy_id,
        policy.policy_version,
        policy.model_dump(mode="json", serialize_as_any=True),
    )
    case_snapshot = _snapshot(
        "assurance_case",
        assurance_case.assurance_case_id,
        assurance_case.schema_version,
        assurance_case.model_dump(mode="json"),
    )
    boundaries = _boundary_conditions(assurance_case, subject_type)
    snapshots = [
        policy_snapshot,
        case_snapshot,
        _snapshot(
            "rule_registry",
            "intentforge_bracket_rules",
            "1.0",
            {"rules": list(resources.rules), "rule_sources": resources.rule_sources},
        ),
        _snapshot(
            "capability_registry",
            "intentforge_capability_manifest",
            capability_version,
            resources.capability_manifest,
        ),
        _snapshot(
            "evidence_registry",
            "intentforge_evidence_manifest",
            evidence_version,
            {"definitions": list(resources.evidence_definitions)},
        ),
        _snapshot(
            "evidence_resolution",
            "intentforge_static_evidence_resolution",
            "1.0",
            {"runtime_verification": False, "observations": list(resources.evidence_observations)},
        ),
        _snapshot(
            "check_registry",
            "intentforge_review_check_registry",
            REVIEW_CHECK_REGISTRY_VERSION,
            check_registry_contract(),
        ),
        _snapshot(
            "decision_strategy",
            policy.decision_strategy,
            "1.0",
            DECISION_PRECEDENCE_CONTRACT,
        ),
        _snapshot(
            "audit_package_observation",
            "review_input_audit_package",
            "1.0",
            _stable_package_result(package_result),
        ),
        _snapshot(
            "boundary_conditions",
            assurance_case.assurance_case_id,
            "1.0",
            boundaries,
        ),
    ]
    by_type = {item.snapshot_type: item for item in snapshots}
    nodes: list[ReviewExecutionNode] = [
        ReviewExecutionNode(
            sequence=0,
            node_type="input_validation",
            node_key="assurance_case_validation",
            status="passed",
            input_content_ids=[case_snapshot.content_id],
            output_content_ids=[assurance_case.content_id],
        ),
        ReviewExecutionNode(
            sequence=1,
            node_type="subject_resolution",
            node_key="subject_type_resolution",
            status="completed",
            input_content_ids=[case_snapshot.content_id],
            observed_value=subject_type,
            expected_value=policy.subject_type,
        ),
        ReviewExecutionNode(
            sequence=2,
            node_type="scope_validation",
            node_key="policy_scope_validation",
            status="passed",
            input_content_ids=[policy_snapshot.content_id, case_snapshot.content_id],
            observed_value={
                "family": assurance_case.cad_family,
                "operation": assurance_case.operation,
                "subject_type": subject_type,
            },
            expected_value={
                "families": policy.applicable_families,
                "operations": policy.applicable_operations,
                "subject_type": policy.subject_type,
            },
        ),
        ReviewExecutionNode(
            sequence=3,
            node_type="evidence_resolution",
            node_key="static_evidence_matrix",
            status="completed",
            input_content_ids=[by_type["evidence_registry"].content_id],
            output_content_ids=[by_type["evidence_resolution"].content_id],
            observed_value={
                "definition_count": len(resources.evidence_definitions),
                "observation_count": len(resources.evidence_observations),
                "statuses": {
                    status: sum(item.get("status") == status for item in resources.evidence_observations)
                    for status in sorted({str(item.get("status")) for item in resources.evidence_observations})
                },
            },
            expected_value={"one_observation_per_definition": True},
        ),
    ]
    findings_by_check = {item.check_id: item for item in findings}
    conditions_by_check = {item.source_check_id: item for item in conditions}
    for sequence, check in enumerate(sorted(policy.checks, key=lambda item: item.check_id), start=4):
        finding = findings_by_check[check.check_id]
        condition = conditions_by_check.get(check.check_id)
        outputs = [finding.content_id]
        if condition is not None:
            outputs.append(condition.content_id)
        nodes.append(
            ReviewExecutionNode(
                sequence=sequence,
                node_type="check_evaluation",
                node_key=f"check:{check.check_id}",
                status=finding.status,
                input_content_ids=[check.content_id, case_snapshot.content_id],
                output_content_ids=outputs,
                check_id=check.check_id,
                check_type=check.check_type,
                parameters=check.parameters.model_dump(mode="json"),
                observed_value=finding.observed_value,
                expected_value=finding.expected_value,
                diagnostics=finding.diagnostics,
            )
        )
    precedence_sequence = len(nodes)
    nodes.append(
        ReviewExecutionNode(
            sequence=precedence_sequence,
            node_type="decision_precedence",
            node_key="deterministic_precedence_v1",
            status="completed",
            input_content_ids=[item.content_id for item in findings],
            output_content_ids=[decision_core_content_id],
            observed_value=decision_status,
            expected_value=DECISION_PRECEDENCE_CONTRACT["ordered_rules"],
        )
    )
    nodes.append(
        ReviewExecutionNode(
            sequence=precedence_sequence + 1,
            node_type="decision_assembly",
            node_key="review_decision_assembly",
            status="completed",
            input_content_ids=[decision_core_content_id, policy_snapshot.content_id, case_snapshot.content_id],
            output_content_ids=[decision_core_content_id],
            observed_value={"decision_status": decision_status},
            expected_value={"deterministic": True},
        )
    )
    return DecisionProvenance(
        tool_version=resources.tool_version,
        check_registry_content_id=check_registry_content_id(),
        decision_strategy=policy.decision_strategy,
        decision_strategy_content_id=decision_strategy_content_id(),
        policy_snapshot_id=policy_snapshot.snapshot_id,
        assurance_case_snapshot_id=case_snapshot.snapshot_id,
        snapshots=snapshots,
        execution_nodes=nodes,
        active_boundary_conditions=boundaries,
        evidence_definition_count=len(resources.evidence_definitions),
        evidence_observation_count=len(resources.evidence_observations),
        runtime_metadata=runtime_metadata or {},
    )


def resources_from_provenance(provenance: DecisionProvenance) -> ReviewEvaluationResources:
    rule_payload = provenance.snapshot("rule_registry").payload
    capability_payload = provenance.snapshot("capability_registry").payload
    evidence_payload = provenance.snapshot("evidence_registry").payload
    observation_payload = provenance.snapshot("evidence_resolution").payload
    return ReviewEvaluationResources(
        rules=tuple(rule_payload.get("rules", [])),
        rule_sources=dict(rule_payload.get("rule_sources", {})),
        capability_manifest=dict(capability_payload),
        evidence_definitions=tuple(evidence_payload.get("definitions", [])),
        evidence_observations=tuple(observation_payload.get("observations", [])),
        tool_version=provenance.tool_version,
    )


def package_result_from_provenance(provenance: DecisionProvenance) -> dict[str, Any] | None:
    payload = provenance.snapshot("audit_package_observation").payload
    if not payload.get("supplied"):
        return None
    result = payload.get("result")
    return dict(result) if isinstance(result, dict) else None


def verify_decision_provenance(
    decision: ReviewDecision | dict[str, Any],
    *,
    perform_replay: bool = True,
) -> DecisionProvenanceVerification:
    """Verify snapshot integrity and optionally replay from frozen inputs only."""

    record = decision if isinstance(decision, ReviewDecision) else ReviewDecision.model_validate(decision)
    provenance = record.decision_provenance
    if provenance is None:
        return DecisionProvenanceVerification(
            passed=False,
            status="missing",
            errors=["review decision does not contain deterministic provenance"],
        )
    errors: list[str] = []
    warnings: list[str] = []
    snapshot_mismatches = 0
    node_mismatches = 0
    for snapshot in provenance.snapshots:
        try:
            FrozenDecisionSnapshot.model_validate(snapshot.model_dump(mode="json"))
        except ValueError as exc:
            snapshot_mismatches += 1
            errors.append(str(exc))
    for node in provenance.execution_nodes:
        try:
            ReviewExecutionNode.model_validate(node.model_dump(mode="json"))
        except ValueError as exc:
            node_mismatches += 1
            errors.append(str(exc))
    supported = (
        provenance.schema_version == REVIEW_PROVENANCE_SCHEMA_VERSION
        and provenance.evaluator_version == REVIEW_EVALUATOR_VERSION
        and provenance.check_registry_version == REVIEW_CHECK_REGISTRY_VERSION
        and provenance.check_registry_content_id == check_registry_content_id()
        and provenance.decision_strategy == DECISION_PRECEDENCE_CONTRACT["strategy"]
        and provenance.decision_strategy_content_id == decision_strategy_content_id()
    )
    if not supported:
        warnings.append("recorded review engine contract is not supported by this runtime")
    try:
        policy_snapshot = provenance.snapshot("review_policy")
        case_snapshot = provenance.snapshot("assurance_case")
        if policy_snapshot.content_id != canonical_digest("decision_snapshot_content", policy_snapshot.payload):
            errors.append("policy snapshot content mismatch")
        if case_snapshot.content_id != canonical_digest("decision_snapshot_content", case_snapshot.payload):
            errors.append("assurance case snapshot content mismatch")
        if policy_snapshot.payload.get("content_id") != record.policy_content_id:
            errors.append("decision policy content does not match frozen policy")
        if case_snapshot.payload.get("content_id") != record.assurance_case_content_id:
            errors.append("decision assurance content does not match frozen assurance case")
    except (ValueError, AttributeError) as exc:
        errors.append(str(exc))
    evidence_registry = provenance.snapshot("evidence_registry").payload
    evidence_resolution = provenance.snapshot("evidence_resolution").payload
    definitions = evidence_registry.get("definitions", []) if isinstance(evidence_registry, dict) else []
    observations = evidence_resolution.get("observations", []) if isinstance(evidence_resolution, dict) else []
    if len(definitions) != provenance.evidence_definition_count:
        errors.append("evidence definition count does not match provenance")
    if len(observations) != provenance.evidence_observation_count:
        errors.append("evidence observation count does not match provenance")
    if {item.get("evidence_id") for item in definitions} != {item.get("evidence_id") for item in observations}:
        errors.append("frozen evidence definition and observation matrices do not align")

    replay_performed = False
    replay_decision_id = None
    replay_mismatches = 0
    if perform_replay and supported and not errors:
        try:
            from intentforge.review.evaluator import evaluate_assurance_case

            policy = ReviewPolicy.model_validate(provenance.snapshot("review_policy").payload)
            case = AssuranceCase.model_validate(provenance.snapshot("assurance_case").payload)
            replay = evaluate_assurance_case(
                policy,
                case,
                package_result_from_provenance(provenance),
                resources=resources_from_provenance(provenance),
                runtime_metadata=record.runtime_metadata,
            )
            replay_performed = True
            replay_decision_id = replay.decision_id
            if replay.content_id != record.content_id or replay.decision_id != record.decision_id:
                replay_mismatches += 1
                errors.append("replayed review decision identity mismatch")
            if replay.decision_provenance is None or replay.decision_provenance.content_id != provenance.content_id:
                replay_mismatches += 1
                errors.append("replayed decision provenance identity mismatch")
        except (ValueError, KeyError, TypeError) as exc:
            replay_mismatches += 1
            errors.append(f"deterministic replay failed: {exc}")
    status = "failed" if errors else "verified" if supported else "unsupported"
    return DecisionProvenanceVerification(
        passed=status == "verified" and (not perform_replay or replay_performed),
        status=status,
        provenance_id=provenance.provenance_id,
        replay_supported=supported,
        replay_performed=replay_performed,
        replay_decision_id=replay_decision_id,
        snapshot_count=len(provenance.snapshots),
        execution_node_count=len(provenance.execution_nodes),
        evidence_definition_count=len(definitions),
        evidence_observation_count=len(observations),
        snapshot_mismatch_count=snapshot_mismatches,
        execution_node_mismatch_count=node_mismatches,
        replay_mismatch_count=replay_mismatches,
        errors=errors,
        warnings=warnings,
        metrics={
            "snapshot_mismatch_count": snapshot_mismatches,
            "execution_node_mismatch_count": node_mismatches,
            "replay_mismatch_count": replay_mismatches,
            "evidence_definition_count": len(definitions),
            "evidence_observation_count": len(observations),
        },
    )
