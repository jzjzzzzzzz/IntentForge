import json

import pytest

from intentforge.cli import main


def test_knowledge_reasoning_info_cli(capsys) -> None:
    result = main(["knowledge", "reasoning-info"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Engineering reasoning engine" in output
    assert "deterministic" in output


def test_knowledge_reasoning_validate_cli(capsys) -> None:
    result = main(["knowledge", "reasoning-validate"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Engineering reasoning validation" in output
    assert "PASS" in output


def test_design_review_reasoning_cli(capsys) -> None:
    pytest.importorskip("cadquery")

    result = main(["design-review", "wall_mounted_bracket", "--knowledge", "--reasoning"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Reasoning report:" in output


def test_design_review_reasoning_json_cli(capsys) -> None:
    pytest.importorskip("cadquery")

    result = main(["design-review", "wall_mounted_bracket", "--knowledge", "--reasoning", "--json"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Reasoning JSON report:" in output
    with open("output/design_review_report.json", encoding="utf-8") as report_file:
        report = json.load(report_file)
    assert report["reasoning_report"]["reasoning_version"] == "1.0"


def test_reasoning_auto_enables_knowledge(capsys) -> None:
    pytest.importorskip("cadquery")

    result = main(["design-review", "l_bracket", "--reasoning"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Knowledge findings:" in output
    assert "Reasoning report:" in output


def test_existing_design_review_without_reasoning_remains_unchanged(capsys) -> None:
    pytest.importorskip("cadquery")

    result = main(["design-review", "wall_mounted_bracket", "--knowledge"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Knowledge findings:" in output
    assert "Reasoning report:" not in output
