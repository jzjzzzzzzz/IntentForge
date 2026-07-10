from reasoning_test_helpers import reasoning_report


def test_fixed_size_spacing_conflict_detected() -> None:
    report = reasoning_report(["hole_edge_margin_001", "hole_spacing_001"])

    assert report.conflicts
    assert any(conflict.conflict_type == "geometry_constraint_conflict" for conflict in report.conflicts)


def test_conflict_includes_rule_ids_and_resolution_strategy() -> None:
    report = reasoning_report(["hole_edge_margin_001", "hole_spacing_001"])
    conflict = report.conflicts[0]

    assert {"hole_edge_margin_001", "hole_spacing_001"} <= set(conflict.rule_ids)
    assert conflict.resolution_strategy


def test_no_conflict_without_supporting_findings() -> None:
    report = reasoning_report(["hole_edge_margin_001"])

    assert report.conflicts == []
