from intentforge.knowledge.evidence_registry import load_evidence_definitions
from intentforge.knowledge.evidence_resolver import resolve_evidence, resolve_evidence_definition


def test_default_evidence_resolves() -> None:
    report = resolve_evidence()
    assert report.evidence_count == len(load_evidence_definitions())
    assert report.summary["unresolved_evidence_count"] == 0
    assert report.summary["failed_evidence_count"] == 0


def test_unknown_reference_unresolved_not_crash() -> None:
    definition = load_evidence_definitions()[0].model_copy(update={"reference": "missing_rule_id"})
    observation = resolve_evidence_definition(definition)
    assert observation.status == "unresolved"
    assert not observation.matches_expectation


def test_runtime_verification_report_distinguishes_mode() -> None:
    report = resolve_evidence(runtime=True)
    assert report.runtime_verification is True
    assert report.evidence_count > 0
    assert report.summary["failed_evidence_count"] == 0
