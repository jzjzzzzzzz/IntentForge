from intentforge.knowledge import compile_rule, compile_rules, load_rules


def test_compile_rule_outputs_constraint() -> None:
    rule = next(rule for rule in load_rules() if rule.id == "hole_edge_margin_001")

    constraint = compile_rule(rule)

    assert constraint.rule_id == "hole_edge_margin_001"
    assert constraint.expression == "hole_edge_distance >= 1.5 * hole_diameter"
    assert constraint.source == "engineering_rule"
    assert constraint.confidence == rule.confidence


def test_compile_rules_preserves_order() -> None:
    rules = load_rules()
    constraints = compile_rules(rules)

    assert [constraint.rule_id for constraint in constraints] == [rule.id for rule in rules]
