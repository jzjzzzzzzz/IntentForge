"""Engineering knowledge rules for IntentForge design review."""

from intentforge.knowledge.compiler import compile_rule, compile_rules
from intentforge.knowledge.evaluator import (
    build_design_metrics,
    evaluate_design,
    evaluate_expression,
    evaluate_parameter_table,
)
from intentforge.knowledge.provenance import RuleProvenance, provenance_from_rule
from intentforge.knowledge.report import KnowledgeReport, make_knowledge_report, write_knowledge_report
from intentforge.knowledge.rationale import generate_design_rationale
from intentforge.knowledge.rules import RuleRegistry, load_rules, validate_rule_data
from intentforge.knowledge.schema import CompiledConstraint, DesignKnowledgeRule, KnowledgeFinding

__all__ = [
    "CompiledConstraint",
    "DesignKnowledgeRule",
    "KnowledgeFinding",
    "KnowledgeReport",
    "RuleProvenance",
    "RuleRegistry",
    "build_design_metrics",
    "compile_rule",
    "compile_rules",
    "evaluate_design",
    "evaluate_expression",
    "evaluate_parameter_table",
    "generate_design_rationale",
    "load_rules",
    "make_knowledge_report",
    "provenance_from_rule",
    "validate_rule_data",
    "write_knowledge_report",
]
