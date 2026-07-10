import pytest

from intentforge.example_data import load_example_json, load_example_yaml
from intentforge.knowledge import (
    RuleRegistry,
    build_design_metrics,
    build_engineering_reasoning_report,
    evaluate_parameter_table,
    make_knowledge_report,
)
from intentforge.reports.design_review import generate_design_review_report
from intentforge.schemas import FeaturePlan, IntentSpec, ParameterTable


def test_design_review_accepts_reasoning_report() -> None:
    parameter_table = ParameterTable.model_validate(load_example_yaml("bracket_params.yaml"))
    feature_plan = FeaturePlan.model_validate(load_example_json("bracket_feature_plan.json"))
    intent = IntentSpec.model_validate(load_example_json("bracket_intent.json"))
    registry = RuleRegistry.load()
    findings = evaluate_parameter_table(parameter_table, feature_plan)
    knowledge_report = make_knowledge_report(findings, rules_checked=registry.count())
    reasoning_report = build_engineering_reasoning_report(
        model_family=parameter_table.family,
        knowledge_report=knowledge_report,
        rule_registry=registry,
        metrics=build_design_metrics(parameter_table, feature_plan),
    )

    report = generate_design_review_report(
        intent_spec=intent,
        parameter_table=parameter_table,
        feature_plan=feature_plan,
        knowledge_findings=findings,
        knowledge_report=knowledge_report.model_dump(mode="json"),
        reasoning_report=reasoning_report.model_dump(mode="json"),
    )

    assert report["reasoning_report"]["report_id"] == reasoning_report.report_id


def test_cli_json_reasoning_output_contract(capsys) -> None:
    pytest.importorskip("cadquery")
    from intentforge.cli import main

    result = main(["design-review", "l_bracket", "--knowledge", "--reasoning", "--json"])

    assert result == 0
    assert "Reasoning JSON report:" in capsys.readouterr().out
