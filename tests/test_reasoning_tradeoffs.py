from reasoning_test_helpers import reasoning_report


def test_relevant_tradeoff_generated() -> None:
    report = reasoning_report(["hole_edge_margin_001"])

    assert report.tradeoffs
    assert "plate_width" in report.tradeoffs[0].affected_parameters
    assert report.tradeoffs[0].confidence > 0


def test_irrelevant_tradeoff_not_generated_for_passed_rule() -> None:
    report = reasoning_report([], passed_rule_ids=["hole_edge_margin_001"])

    assert report.tradeoffs == []


def test_cutout_tradeoff_includes_affected_parameters() -> None:
    report = reasoning_report(["cutout_stiffness_tradeoff_001"])

    tradeoff = report.tradeoffs[0]
    assert "cutout_width" in tradeoff.affected_parameters
    assert tradeoff.benefit
    assert tradeoff.cost
