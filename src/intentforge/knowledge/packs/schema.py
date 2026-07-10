"""Stable schemas for engineering knowledge rule packs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from intentforge.knowledge.schema import DesignKnowledgeRule


KNOWN_RULE_PACK_CATEGORIES = ("mechanical", "manufacturing", "assembly", "structural")
SUPPORTED_RULE_PACK_FAMILIES = ("wall_mounted_bracket", "l_bracket")
RulePackStatus = Literal["active", "deprecated"]


class RulePack(BaseModel):
    """Versioned, auditable group of engineering knowledge rules."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    pack_id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    pack_version: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    supported_model_families: list[str] = Field(..., min_length=1)
    status: RulePackStatus = "active"
    rules: list[DesignKnowledgeRule] = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None

    @field_validator("pack_id")
    @classmethod
    def validate_pack_id(cls, value: str) -> str:
        unstable_tokens = {"uuid", "random", "tmp", "temp"}
        if any(token in value for token in unstable_tokens):
            raise ValueError("pack_id must be stable and human-readable")
        return value

    @field_validator("pack_version")
    @classmethod
    def validate_pack_version(cls, value: str) -> str:
        parts = value.split(".")
        if not parts or not all(part.isdigit() for part in parts):
            raise ValueError("pack_version must use numeric dot notation, for example '1.0'")
        return value

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        if value not in KNOWN_RULE_PACK_CATEGORIES:
            raise ValueError(f"unsupported rule pack category: {value}")
        return value

    @field_validator("supported_model_families")
    @classmethod
    def validate_supported_model_families(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - set(SUPPORTED_RULE_PACK_FAMILIES))
        if unknown:
            raise ValueError(f"unsupported model family: {', '.join(unknown)}")
        return value

    @model_validator(mode="after")
    def validate_rule_pack(self) -> "RulePack":
        rule_ids = [rule.id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("duplicate rule id inside rule pack")

        mismatched_categories = sorted({rule.id for rule in self.rules if rule.category != self.category})
        if mismatched_categories:
            raise ValueError(
                "rules must match pack category unless split into another pack: "
                + ", ".join(mismatched_categories)
            )

        family_set = set(self.supported_model_families)
        unsupported_rule_families = sorted(
            {
                rule.id
                for rule in self.rules
                if not set(rule.applies_to).issubset(family_set)
            }
        )
        if unsupported_rule_families:
            raise ValueError(
                "rules must not apply to families outside supported_model_families: "
                + ", ".join(unsupported_rule_families)
            )
        return self
