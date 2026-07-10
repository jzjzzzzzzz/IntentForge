from intentforge.knowledge.coverage import build_capability_matrix


def test_capability_matrix_contains_expected_rows() -> None:
    matrix = build_capability_matrix()

    ids = {row.capability_id for row in matrix.rows}
    assert "wall_two_hole_symmetric_horizontal_pattern" in ids
    assert "l_basic_right_angle_bracket_generation" in ids
    assert matrix.summary["capability_count"] == 28


def test_capability_matrix_filters_by_family() -> None:
    matrix = build_capability_matrix(family="l_bracket")

    assert matrix.rows
    assert {row.family for row in matrix.rows} == {"l_bracket"}
    assert matrix.summary["by_family"] == {"l_bracket": 13}


def test_capability_matrix_filters_by_status() -> None:
    matrix = build_capability_matrix(status="unsupported")

    assert matrix.rows
    assert {row.status for row in matrix.rows} == {"unsupported"}
    assert all(row.rejection_behavior for row in matrix.rows)


def test_capability_matrix_filters_by_stage() -> None:
    matrix = build_capability_matrix(stage="engineering_reasoning")

    assert matrix.rows
    assert all("engineering_reasoning" in row.stages for row in matrix.rows)


def test_capability_matrix_filters_by_pack_and_rule() -> None:
    by_pack = build_capability_matrix(knowledge_pack="bracket_mechanical")
    by_rule = build_capability_matrix(rule_id="gusset_recommendation_001")

    assert by_pack.rows
    assert all("bracket_mechanical" in row.knowledge_packs for row in by_pack.rows)
    assert by_rule.rows
    assert all("gusset_recommendation_001" in row.rule_ids for row in by_rule.rows)


def test_capability_matrix_json_serializes() -> None:
    matrix = build_capability_matrix(family="wall_mounted_bracket", status="supported")
    text = matrix.to_json()

    assert '"matrix_id"' in text
    assert '"wall_mounted_bracket"' in text
