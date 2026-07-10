from reasoning_test_helpers import reasoning_report


def test_duplicate_recommendations_merged() -> None:
    report = reasoning_report(["hole_edge_margin_001", "hole_spacing_001"])

    ids = [recommendation.recommendation_id for recommendation in report.recommendations]
    assert len(ids) == len(set(ids))


def test_conflicting_recommendations_surfaced() -> None:
    report = reasoning_report(["hole_edge_margin_001", "hole_spacing_001"])

    assert report.conflicts
    assert any("plate width" in recommendation.action.lower() for recommendation in report.recommendations)


def test_affected_parameters_preserved() -> None:
    report = reasoning_report(["hole_edge_margin_001"])

    assert "plate_width" in report.recommendations[0].affected_parameters


def test_recommendations_include_limitations() -> None:
    report = reasoning_report(["hole_edge_margin_001"])

    assert report.recommendations[0].limitations
