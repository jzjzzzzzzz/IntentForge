from reasoning_test_helpers import reasoning_report


def test_identical_input_produces_identical_report_id() -> None:
    first = reasoning_report(["hole_edge_margin_001", "hole_spacing_001"])
    second = reasoning_report(["hole_edge_margin_001", "hole_spacing_001"])

    assert first.report_id == second.report_id


def test_stable_recommendation_ordering() -> None:
    first = reasoning_report(["hole_edge_margin_001", "hole_spacing_001", "fastener_accessibility_001"])
    second = reasoning_report(["hole_edge_margin_001", "hole_spacing_001", "fastener_accessibility_001"])

    assert [item.recommendation_id for item in first.recommendations] == [
        item.recommendation_id for item in second.recommendations
    ]


def test_stable_interaction_ordering() -> None:
    first = reasoning_report(["hole_edge_margin_001", "hole_spacing_001", "fastener_accessibility_001"])
    second = reasoning_report(["hole_edge_margin_001", "hole_spacing_001", "fastener_accessibility_001"])

    assert [item.interaction_id for item in first.interactions] == [
        item.interaction_id for item in second.interactions
    ]


def test_no_random_ids() -> None:
    report = reasoning_report(["hole_edge_margin_001"])

    assert "uuid" not in report.report_id
    assert "random" not in report.report_id
