from intentforge.knowledge.schema import CompiledConstraint, DesignKnowledgeRule, KnowledgeFinding


def test_design_knowledge_rule_schema() -> None:
    rule = DesignKnowledgeRule(
        id="hole_edge_margin_test",
        name="Hole Edge Margin",
        category="mechanical",
        description="Edge distance should be large enough.",
        applies_to=["wall_mounted_bracket"],
        condition={"expression": "hole_edge_distance >= 1.5 * hole_diameter"},
        severity="warning",
        recommendation="Increase edge distance.",
        source_reference="unit test",
        confidence=0.9,
    )

    assert rule.id == "hole_edge_margin_test"
    assert rule.confidence == 0.9


def test_knowledge_finding_schema() -> None:
    finding = KnowledgeFinding(
        rule_id="rule_001",
        rule_name="Rule",
        category="mechanical",
        severity="warning",
        passed=False,
        message="Rule failed.",
        recommendation="Fix it.",
        confidence=0.8,
        metadata={"expression": "a >= b"},
    )

    assert finding.passed is False
    assert finding.metadata["expression"] == "a >= b"


def test_compiled_constraint_schema() -> None:
    constraint = CompiledConstraint(
        rule_id="rule_001",
        expression="hole_spacing >= 3 * hole_diameter",
        source="engineering_rule",
        confidence=0.86,
    )

    assert constraint.expression == "hole_spacing >= 3 * hole_diameter"
