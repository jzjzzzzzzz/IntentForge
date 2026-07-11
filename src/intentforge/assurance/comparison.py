"""Structured deterministic assurance-case comparisons."""

from __future__ import annotations

from typing import Any

from intentforge.assurance.schema import AssuranceCase, canonical_digest


def compare_assurance_cases(first: AssuranceCase | dict, second: AssuranceCase | dict) -> dict[str, Any]:
    a = first if isinstance(first, AssuranceCase) else AssuranceCase.model_validate(first)
    b = second if isinstance(second, AssuranceCase) else AssuranceCase.model_validate(second)
    fields = {
        "structured_intent": (a.structured_intent, b.structured_intent),
        "feature_plan": (a.feature_plan_summary, b.feature_plan_summary),
        "constraints": (a.compiled_constraint_summary, b.compiled_constraint_summary),
        "rules": (a.rule_references, b.rule_references),
        "validations": ([x.model_dump(mode="json") for x in a.validation_observations], [x.model_dump(mode="json") for x in b.validation_observations]),
        "limitations": ([x.model_dump(mode="json") for x in a.limitations], [x.model_dump(mode="json") for x in b.limitations]),
        "artifacts": ([x.model_dump(mode="json") for x in a.artifact_records], [x.model_dump(mode="json") for x in b.artifact_records]),
        "overall_status": (a.overall_assurance_status, b.overall_assurance_status),
    }
    changes = {name: {"before": values[0], "after": values[1]} for name, values in fields.items() if values[0] != values[1]}
    identity = {"first": a.content_id, "second": b.content_id, "changed_fields": sorted(changes)}
    return {"comparison_id": canonical_digest("assurance_comparison", identity), "identical": not changes,
            "first_case_id": a.assurance_case_id, "second_case_id": b.assurance_case_id,
            "changed_fields": sorted(changes), "changes": changes}
