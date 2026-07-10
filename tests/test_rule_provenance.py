from intentforge.knowledge import RuleProvenance, load_rules, provenance_from_rule


def test_rule_provenance_from_rule() -> None:
    rule = next(rule for rule in load_rules() if rule.id == "hole_edge_margin_001")

    provenance = provenance_from_rule(rule)

    assert isinstance(provenance, RuleProvenance)
    assert provenance.rule_id == rule.id
    assert provenance.source == rule.source_reference
    assert provenance.confidence == rule.confidence
    assert provenance.verification_level == "heuristic"
