import json
from pathlib import Path

from intentforge.cli import main


def test_reasoning_verify_cli_writes_report(capsys) -> None:
    result = main(["knowledge", "reasoning-verify"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Engineering reasoning verification" in output
    assert "Passed: 10" in output
    report_path = Path("output/harness/reasoning_verification_report.json")
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["failed"] == 0


def test_reasoning_benchmark_cli_writes_report(capsys) -> None:
    result = main(["knowledge", "reasoning-benchmark"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Engineering reasoning benchmark" in output
    assert "Contradictions: 0" in output
    report_path = Path("output/harness/reasoning_benchmark_report.json")
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["pass_rate"] == 1.0
