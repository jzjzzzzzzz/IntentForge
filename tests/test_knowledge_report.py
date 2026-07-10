import json

from intentforge.knowledge import KnowledgeFinding, make_knowledge_report, write_knowledge_report


def _finding() -> KnowledgeFinding:
    return KnowledgeFinding(
        rule_id="hole_edge_margin_001",
        rule_name="Hole Edge Margin",
        category="mechanical",
        severity="warning",
        passed=False,
        message="Hole edge margin is below recommendation.",
        recommendation="Increase edge distance.",
        confidence=0.85,
        metadata={"rule_version": "1.0"},
    )


def test_knowledge_report_serializes_to_json() -> None:
    report = make_knowledge_report([_finding()], rules_checked=10, timestamp="2026-07-10T00:00:00+08:00")
    data = json.loads(report.to_json())

    assert data["rules_checked"] == 10
    assert data["findings"][0]["rule_id"] == "hole_edge_margin_001"
    assert data["summary"]["advisory_findings"] == 1


def test_knowledge_report_id_is_stable_for_same_findings() -> None:
    report_a = make_knowledge_report([_finding()], rules_checked=10, timestamp="2026-07-10T00:00:00+08:00")
    report_b = make_knowledge_report([_finding()], rules_checked=10, timestamp="2026-07-10T00:01:00+08:00")

    assert report_a.report_id == report_b.report_id


def test_write_knowledge_report(tmp_path) -> None:
    report = make_knowledge_report([_finding()], rules_checked=10)
    path = write_knowledge_report(report, tmp_path / "knowledge_report.json")

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["report_id"] == report.report_id
