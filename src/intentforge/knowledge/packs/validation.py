"""Validation helpers for engineering knowledge rule packs."""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from intentforge.knowledge.packs.loader import load_default_bracket_rule_packs
from intentforge.knowledge.packs.schema import KNOWN_RULE_PACK_CATEGORIES, SUPPORTED_RULE_PACK_FAMILIES, RulePack


class RulePackValidationResult(BaseModel):
    """Structured validation result for rule pack integrity."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    packs_checked: int
    rules_checked: int
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


def _add_error(errors: list[dict[str, Any]], message: str, **context: Any) -> None:
    errors.append({"message": message, **{key: value for key, value in context.items() if value is not None}})


def _validate_reasoning_references(pack: RulePack, rule_ids: set[str], errors: list[dict[str, Any]]) -> None:
    reference_fields = (
        "can_conflict_with",
        "depends_on",
        "duplicates",
        "mitigates",
        "mitigated_by",
        "reinforces",
    )
    for rule in pack.rules:
        for field_name in reference_fields:
            references = rule.reasoning.get(field_name, []) or []
            seen: set[str] = set()
            for reference in references:
                if reference in seen:
                    _add_error(
                        errors,
                        f"duplicate reasoning reference: {reference}",
                        pack_id=pack.pack_id,
                        rule_id=rule.id,
                        field=f"reasoning.{field_name}",
                    )
                seen.add(reference)
                if reference not in rule_ids:
                    _add_error(
                        errors,
                        f"unknown referenced rule id: {reference}",
                        pack_id=pack.pack_id,
                        rule_id=rule.id,
                        field=f"reasoning.{field_name}",
                    )


def validate_rule_packs(packs: Iterable[RulePack]) -> RulePackValidationResult:
    """Validate loaded rule packs and cross-pack references."""

    pack_list = list(packs)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen_pack_ids: set[str] = set()
    seen_rule_ids: set[str] = set()
    duplicate_pack_count = 0
    duplicate_rule_count = 0
    deprecated_pack_count = 0
    rules_checked = 0

    for pack in pack_list:
        try:
            RulePack.model_validate(pack.model_dump(mode="json"))
        except ValidationError as exc:
            for error in exc.errors():
                _add_error(
                    errors,
                    error.get("msg", "invalid rule pack"),
                    pack_id=getattr(pack, "pack_id", None),
                    field=".".join(str(part) for part in error.get("loc", [])),
                )

        if pack.pack_id in seen_pack_ids:
            duplicate_pack_count += 1
            _add_error(errors, f"duplicate rule pack id: {pack.pack_id}", pack_id=pack.pack_id)
        seen_pack_ids.add(pack.pack_id)
        if pack.status == "deprecated":
            deprecated_pack_count += 1
            warnings.append({"pack_id": pack.pack_id, "message": "deprecated pack loaded"})
        if pack.category not in KNOWN_RULE_PACK_CATEGORIES:
            _add_error(errors, f"unsupported category: {pack.category}", pack_id=pack.pack_id)
        unknown_families = sorted(set(pack.supported_model_families) - set(SUPPORTED_RULE_PACK_FAMILIES))
        for family in unknown_families:
            _add_error(errors, f"unsupported model family: {family}", pack_id=pack.pack_id)

        local_rule_ids: set[str] = set()
        if not pack.rules:
            _add_error(errors, "rule pack must contain at least one rule", pack_id=pack.pack_id)
        for rule in pack.rules:
            rules_checked += 1
            if rule.id in local_rule_ids:
                duplicate_rule_count += 1
                _add_error(errors, f"duplicate rule id inside pack: {rule.id}", pack_id=pack.pack_id, rule_id=rule.id)
            local_rule_ids.add(rule.id)
            if rule.id in seen_rule_ids:
                duplicate_rule_count += 1
                _add_error(errors, f"duplicate rule id across packs: {rule.id}", pack_id=pack.pack_id, rule_id=rule.id)
            seen_rule_ids.add(rule.id)
            if rule.category != pack.category:
                _add_error(
                    errors,
                    f"rule category {rule.category} does not match pack category {pack.category}",
                    pack_id=pack.pack_id,
                    rule_id=rule.id,
                )
            if not rule.source_reference:
                _add_error(errors, "missing source reference", pack_id=pack.pack_id, rule_id=rule.id)

    _validate_reasoning_references_for_all(pack_list, seen_rule_ids, errors)
    unknown_reference_count = len([error for error in errors if "unknown referenced rule id" in error["message"]])

    return RulePackValidationResult(
        passed=not errors,
        packs_checked=len(pack_list),
        rules_checked=rules_checked,
        errors=errors,
        warnings=warnings,
        summary={
            "active_pack_count": len([pack for pack in pack_list if pack.status == "active"]),
            "active_rule_count": len([rule for pack in pack_list if pack.status == "active" for rule in pack.rules if rule.status == "active"]),
            "duplicate_pack_id_count": duplicate_pack_count,
            "duplicate_rule_id_count": duplicate_rule_count,
            "deprecated_pack_count": deprecated_pack_count,
            "unknown_rule_reference_count": unknown_reference_count,
        },
    )


def _validate_reasoning_references_for_all(
    pack_list: list[RulePack],
    rule_ids: set[str],
    errors: list[dict[str, Any]],
) -> None:
    for pack in pack_list:
        _validate_reasoning_references(pack, rule_ids, errors)


def validate_default_rule_packs() -> RulePackValidationResult:
    """Validate the packaged default bracket rule packs."""

    try:
        packs = load_default_bracket_rule_packs(include_deprecated=True)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        return RulePackValidationResult(
            passed=False,
            packs_checked=0,
            rules_checked=0,
            errors=[{"message": str(exc)}],
            warnings=[],
            summary={
                "active_pack_count": 0,
                "active_rule_count": 0,
                "duplicate_pack_id_count": 0,
                "duplicate_rule_id_count": 0,
                "deprecated_pack_count": 0,
                "unknown_rule_reference_count": 0,
            },
        )
    return validate_rule_packs(packs)
