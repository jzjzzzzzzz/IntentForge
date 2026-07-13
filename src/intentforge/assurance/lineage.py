"""Deterministic predecessor binding for assurance claims and cases."""

from __future__ import annotations

from intentforge.assurance.claims import make_claim
from intentforge.assurance.schema import (
    AssuranceCase,
    canonical_digest,
    validate_content_address,
)


def attach_assurance_predecessor(
    case: AssuranceCase | dict,
    predecessor_hash_pointer: str | None,
) -> AssuranceCase:
    """Bind a validated predecessor address into every run-level claim."""

    record = case if isinstance(case, AssuranceCase) else AssuranceCase.model_validate(case)
    pointer = validate_content_address(predecessor_hash_pointer)
    if record.predecessor_hash_pointer not in {None, pointer}:
        raise ValueError("assurance case is already bound to a different predecessor")
    if pointer is None:
        return record
    claims = []
    arguments = []
    for claim in sorted(record.claims, key=lambda item: item.claim_id):
        rebuilt_claim, rebuilt_argument = make_claim(
            claim.claim_type,
            family=claim.family,
            status=claim.status,
            stages=claim.stages,
            capability_ids=claim.capability_ids,
            evidence_ids=claim.supporting_evidence_ids,
            validation_ids=claim.supporting_validation_ids,
            artifact_ids=claim.supporting_artifact_ids,
            rule_ids=claim.rule_ids,
            limitations=claim.limitations,
            required_review=claim.required_review,
            predecessor_hash_pointer=pointer,
        )
        claims.append(rebuilt_claim)
        arguments.append(rebuilt_argument)
    provisional = record.model_copy(update={
        "assurance_case_id": "pending",
        "content_id": "pending",
        "predecessor_hash_pointer": pointer,
        "claims": sorted(claims, key=lambda item: item.claim_id),
        "arguments": sorted(arguments, key=lambda item: item.argument_id),
    })
    content_id = canonical_digest("assurance_content", provisional.deterministic_payload())
    return provisional.model_copy(update={
        "assurance_case_id": canonical_digest("assurance_case", {"content_id": content_id}),
        "content_id": content_id,
    })
