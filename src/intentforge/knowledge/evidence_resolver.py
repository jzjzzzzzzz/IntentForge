"""Safe static and runtime evidence resolution for IntentForge evidence manifests."""

from __future__ import annotations

from collections import Counter
from importlib import resources
from typing import Any

from benchmark.run_benchmark import load_benchmark_cases

from intentforge.knowledge.capabilities import load_capability_manifest
from intentforge.knowledge.capability_schema import (
    SUPPORTED_CAPABILITY_FAMILIES,
    SUPPORTED_CAPABILITY_STAGES,
    stable_capability_digest,
)
from intentforge.knowledge.coverage import STATIC_EVIDENCE_REFERENCES, validate_capability_manifest
from intentforge.knowledge.evidence_registry import EvidenceRegistry, load_evidence_manifest, validate_evidence_manifest
from intentforge.knowledge.evidence_schema import (
    EvidenceDefinition,
    EvidenceObservation,
    EvidenceResolutionReport,
    EvidenceStatus,
    fixed_evidence_timestamp,
    make_observation,
)
from intentforge.knowledge.packs.validation import validate_default_rule_packs
from intentforge.knowledge.reasoning.benchmark import run_reasoning_benchmark
from intentforge.knowledge.reasoning.verification import load_golden_cases, run_reasoning_verification
from intentforge.knowledge.rules import RuleRegistry
from intentforge.knowledge.packs.registry import RulePackRegistry


KNOWN_PARSER_SUPPORT = {
    "parser:wall_mounted_bracket",
    "parser:l_bracket",
    "parser:unsupported_rejection",
    "parser:edit_workflow",
}
KNOWN_INTENT_SCHEMAS = {
    "schema:ParameterTable",
    "schema:FeatureFlag",
    "schema:CapabilityDefinition",
    "schema:EvidenceDefinition",
}
KNOWN_COMPILERS = {
    "compiler:knowledge_rules",
    "compiler:parameter_constraints",
}
KNOWN_GENERATORS = {
    "generator:wall_mounted_bracket",
    "generator:l_bracket",
}
KNOWN_VALIDATORS = {
    "validator:wall_mounted_bracket",
    "validator:l_bracket",
    "validator:geometry",
    "validator:knowledge",
}
KNOWN_TOPOLOGY_INSPECTORS = {
    "topology:shape_inspector",
    "topology:volume_delta",
}
KNOWN_FEATURE_RECOGNIZERS = {
    "feature_recognizer:wall_mounted_bracket",
    "feature_recognizer:l_bracket",
    "feature_recognizer:through_holes",
    "feature_recognizer:center_cutout",
    "feature_recognizer:l_bracket_gusset",
    "feature_recognizer:solid_connectivity",
}
KNOWN_KNOWLEDGE_EVALUATORS = {
    "knowledge:evaluator",
    "knowledge:report",
    "knowledge:reasoning",
}
KNOWN_TECHNICAL_HARNESS_GATES = {
    "technical_harness:benchmark",
    "technical_harness:sweep",
    "technical_harness:edit_preservation",
    "technical_harness:adversarial_rejection",
    "technical_harness:volume_delta",
    "technical_harness:shape_inspection",
    "technical_harness:feature_recognition",
    "technical_harness:rule_packs",
    "technical_harness:capability_coverage",
    "technical_harness:engineering_reasoning",
    "technical_harness:evidence_trust",
}
KNOWN_REGRESSION_TEST_PREFIXES = ("tests/test_",)


def _benchmark_catalog() -> tuple[set[str], set[str]]:
    cases = load_benchmark_cases()
    benchmark_ids = {str(case["id"]) for case in cases}
    rejection_ids = {
        str(case["id"])
        for case in cases
        if case.get("expected_ok") is False or case.get("category") in {"rejections", "l_rejections"}
    }
    return benchmark_ids, rejection_ids


def _golden_case_ids() -> set[str]:
    return {str(case["id"]) for case in load_golden_cases()}


def _resource_exists(reference: str) -> bool:
    if ":" not in reference:
        return False
    package, resource_name = reference.split(":", 1)
    if not package or not resource_name or "/" in resource_name:
        return False
    try:
        return resources.files(package).joinpath(resource_name).is_file()
    except (ModuleNotFoundError, ValueError):
        return False


def _documentation_reference_known(reference: str) -> bool:
    return reference.startswith("docs/") or reference in {"README.md", "PROJECT_STATUS.md"}


def _regression_test_reference_known(reference: str) -> bool:
    return reference.startswith(KNOWN_REGRESSION_TEST_PREFIXES) and reference.endswith(".py")


def _static_reference_known(definition: EvidenceDefinition) -> tuple[bool, str]:
    rule_registry = RuleRegistry.load()
    pack_registry = RulePackRegistry.load_default()
    capability_manifest = load_capability_manifest()
    rule_ids = {rule.id for rule in rule_registry.get_active_rules()}
    pack_ids = {pack.pack_id for pack in pack_registry.all_packs()}
    capability_ids = {capability.capability_id for capability in capability_manifest.capabilities}
    benchmark_ids, rejection_ids = _benchmark_catalog()
    golden_ids = _golden_case_ids()

    if any(capability_id not in capability_ids for capability_id in definition.capability_ids):
        return False, "unknown capability reference"
    if any(rule_id not in rule_ids for rule_id in definition.rule_ids):
        return False, "unknown rule reference"
    if any(pack_id not in pack_ids for pack_id in definition.pack_ids):
        return False, "unknown pack reference"
    if definition.family and definition.family not in SUPPORTED_CAPABILITY_FAMILIES:
        return False, "unknown family"
    if any(stage not in SUPPORTED_CAPABILITY_STAGES for stage in definition.stages):
        return False, "unknown pipeline stage"

    reference = definition.reference
    evidence_type = definition.evidence_type
    if evidence_type == "rule_definition":
        return reference in rule_ids, "rule id resolves" if reference in rule_ids else "rule id does not resolve"
    if evidence_type == "rule_pack":
        return reference in pack_ids, "rule pack resolves" if reference in pack_ids else "rule pack does not resolve"
    if evidence_type == "parser_support":
        return reference in KNOWN_PARSER_SUPPORT or reference in STATIC_EVIDENCE_REFERENCES.get("parser", set()), "parser support reference checked"
    if evidence_type == "intent_schema":
        return reference in KNOWN_INTENT_SCHEMAS or reference in STATIC_EVIDENCE_REFERENCES.get("schema", set()), "schema reference checked"
    if evidence_type == "constraint_compiler":
        return reference in KNOWN_COMPILERS, "compiler reference checked"
    if evidence_type == "cad_generator":
        return reference in KNOWN_GENERATORS or reference in STATIC_EVIDENCE_REFERENCES.get("generator", set()), "generator reference checked"
    if evidence_type == "geometry_validator":
        return reference in KNOWN_VALIDATORS or reference in STATIC_EVIDENCE_REFERENCES.get("validator", set()), "validator reference checked"
    if evidence_type == "topology_inspector":
        return reference in KNOWN_TOPOLOGY_INSPECTORS or reference in STATIC_EVIDENCE_REFERENCES.get("topology_metric", set()), "topology reference checked"
    if evidence_type == "feature_recognizer":
        return reference in KNOWN_FEATURE_RECOGNIZERS or reference in STATIC_EVIDENCE_REFERENCES.get("feature_recognizer", set()), "feature recognizer reference checked"
    if evidence_type == "knowledge_evaluator":
        return reference in KNOWN_KNOWLEDGE_EVALUATORS, "knowledge evaluator reference checked"
    if evidence_type in {"reasoning_case", "golden_case"}:
        return reference in golden_ids, "golden reasoning case checked"
    if evidence_type == "benchmark_case":
        return reference in benchmark_ids, "benchmark case checked"
    if evidence_type == "rejection_case":
        return reference in rejection_ids, "rejection case checked"
    if evidence_type == "regression_test":
        return _regression_test_reference_known(reference), "regression test identifier checked"
    if evidence_type == "technical_harness_gate":
        return reference in KNOWN_TECHNICAL_HARNESS_GATES, "technical harness gate checked"
    if evidence_type == "documentation":
        return _documentation_reference_known(reference), "documentation reference checked"
    if evidence_type == "package_artifact":
        return _resource_exists(reference), "package artifact checked"
    return False, "unsupported evidence type"


def _freshness_status(definition: EvidenceDefinition) -> EvidenceStatus | None:
    if definition.freshness_policy == "version_match":
        capability_manifest = load_capability_manifest()
        capabilities = {capability.capability_id: capability for capability in capability_manifest.capabilities}
        for capability_id in definition.capability_ids:
            capability = capabilities.get(capability_id)
            if capability is not None and capability.version != definition.version:
                return "stale"
    return None


def resolve_evidence_definition(definition: EvidenceDefinition, *, runtime: bool = False) -> EvidenceObservation:
    """Resolve or verify one evidence definition without executing manifest-selected code."""

    known, diagnostic = _static_reference_known(definition)
    if not known:
        return make_observation(
            definition,
            status="unresolved",
            observed_result=diagnostic,
            matches_expectation=False,
            verifier="static_resolver",
            diagnostics=[diagnostic],
        )
    stale_status = _freshness_status(definition)
    if stale_status is not None:
        return make_observation(
            definition,
            status=stale_status,
            observed_result="version mismatch",
            matches_expectation=False,
            verifier="freshness_resolver",
            diagnostics=["evidence version does not match referenced capability version"],
        )
    if not runtime:
        return make_observation(
            definition,
            status="verified",
            observed_result=diagnostic,
            matches_expectation=True,
            verifier="static_resolver",
            diagnostics=[diagnostic],
        )

    method = definition.verification_method
    if method == "rule_pack_validation":
        result = validate_default_rule_packs()
        return make_observation(
            definition,
            status="verified" if result.passed else "failed",
            observed_result="passed" if result.passed else "failed",
            matches_expectation=result.passed,
            verifier="rule_pack_validation",
            diagnostics=[f"{result.packs_checked} packs checked", f"{len(result.errors)} errors"],
        )
    if method == "capability_validation":
        result = validate_capability_manifest()
        return make_observation(
            definition,
            status="verified" if result.passed else "failed",
            observed_result="passed" if result.passed else "failed",
            matches_expectation=result.passed,
            verifier="capability_validation",
            diagnostics=[f"{result.capabilities_checked} capabilities checked", f"{len(result.errors)} errors"],
        )
    if method == "evidence_manifest_validation":
        result = validate_evidence_manifest()
        return make_observation(
            definition,
            status="verified" if result.passed else "failed",
            observed_result="passed" if result.passed else "failed",
            matches_expectation=result.passed,
            verifier="evidence_manifest_validation",
            diagnostics=[f"{result.evidence_checked} evidence definitions checked", f"{len(result.errors)} errors"],
        )
    if method == "reasoning_golden_verification":
        result = run_reasoning_verification()
        return make_observation(
            definition,
            status="verified" if result["failed"] == 0 else "failed",
            observed_result=f"{result['passed']} passed, {result['failed']} failed",
            matches_expectation=result["failed"] == 0,
            verifier="reasoning_golden_verification",
            diagnostics=[f"{result['total_cases']} golden cases"],
        )
    if method == "reasoning_benchmark":
        result = run_reasoning_benchmark()
        return make_observation(
            definition,
            status="verified" if result["failed"] == 0 else "failed",
            observed_result=f"{result['passed']} passed, {result['failed']} failed",
            matches_expectation=result["failed"] == 0,
            verifier="reasoning_benchmark",
            diagnostics=[f"pass rate {result['pass_rate']:.4f}"],
        )
    return make_observation(
        definition,
        status="verified",
        observed_result=diagnostic,
        matches_expectation=True,
        verifier="static_resolver",
        diagnostics=[diagnostic, "runtime verifier not required for this evidence type"],
    )


def resolve_evidence(
    definitions: list[EvidenceDefinition] | None = None,
    *,
    runtime: bool = False,
) -> EvidenceResolutionReport:
    """Resolve all evidence definitions and produce a deterministic observation report."""

    registry = EvidenceRegistry(definitions or load_evidence_manifest().evidence)
    observations = [resolve_evidence_definition(definition, runtime=runtime) for definition in registry.all()]
    status_counts = Counter(observation.status for observation in observations)
    summary = {
        "runtime_verification": runtime,
        "verified_evidence_count": status_counts.get("verified", 0),
        "failed_evidence_count": status_counts.get("failed", 0),
        "unresolved_evidence_count": status_counts.get("unresolved", 0),
        "unavailable_evidence_count": status_counts.get("unavailable", 0),
        "stale_evidence_count": status_counts.get("stale", 0),
        "not_checked_evidence_count": status_counts.get("not_checked", 0),
    }
    identity = {
        "runtime": runtime,
        "observations": [
            {
                key: value
                for key, value in observation.deterministic_payload().items()
                if key != "diagnostics"
            }
            for observation in observations
        ],
    }
    return EvidenceResolutionReport(
        report_id=stable_capability_digest("evidence_resolution", identity),
        generated_at=fixed_evidence_timestamp(),
        runtime_verification=runtime,
        evidence_count=len(observations),
        observations=observations,
        summary=summary,
    )


def verify_evidence(definitions: list[EvidenceDefinition] | None = None) -> EvidenceResolutionReport:
    """Run safe runtime verification for evidence definitions where available."""

    return resolve_evidence(definitions, runtime=True)
