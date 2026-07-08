import json
import shutil
from pathlib import Path

import pytest

from benchmark.run_benchmark import (
    BENCHMARK_DIR,
    load_benchmark_cases,
    run_benchmark,
    validate_benchmark_cases,
)
import intentforge.cli as cli
from intentforge.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def test_benchmark_files_load() -> None:
    cases = load_benchmark_cases()

    assert len(cases) >= 50
    assert (BENCHMARK_DIR / "prompts" / "clean_prompts.json").exists()
    assert (BENCHMARK_DIR / "expected" / "expected_features.json").exists()
    assert (BENCHMARK_DIR / "expected" / "expected_rejections.json").exists()


def test_every_benchmark_case_has_id_and_type() -> None:
    cases = load_benchmark_cases()

    for case in cases:
        assert case["id"]
        assert case["type"]


def test_duplicate_benchmark_ids_are_rejected() -> None:
    cases = load_benchmark_cases()
    duplicated = cases + [dict(cases[0])]

    with pytest.raises(ValueError, match="duplicate benchmark ids"):
        validate_benchmark_cases(duplicated)


def _copy_benchmark_tree(tmp_path: Path) -> Path:
    copied = tmp_path / "benchmark"
    shutil.copytree(BENCHMARK_DIR, copied)
    return copied


def test_benchmark_runner_produces_report_and_summary(tmp_path: Path) -> None:
    _require_cadquery()

    result = run_benchmark(output_root=tmp_path)

    report_path = tmp_path / "benchmark" / "benchmark_report.json"
    summary_path = tmp_path / "benchmark" / "benchmark_summary.txt"
    persistent_report_path = tmp_path / "benchmark" / "runs" / result["run_id"] / "benchmark_report.json"

    assert report_path.exists()
    assert summary_path.exists()
    assert persistent_report_path.exists()
    assert result["total_cases"] >= 50
    assert result["passed"] + result["failed"] == result["total_cases"]
    assert result["families"]["wall_mounted_bracket"]["passed"] > 0
    assert result["families"]["l_bracket"]["passed"] > 0


def test_benchmark_runner_records_failed_cases_correctly(tmp_path: Path) -> None:
    _require_cadquery()

    benchmark_dir = _copy_benchmark_tree(tmp_path)
    clean_path = benchmark_dir / "prompts" / "clean_prompts.json"
    cases = json.loads(clean_path.read_text(encoding="utf-8"))
    cases[0]["expected_hole_pattern"] = "none"
    clean_path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")

    result = run_benchmark(output_root=tmp_path / "output", benchmark_dir=benchmark_dir)

    assert result["failed"] >= 1
    assert any(case["id"] == "clean_001" for case in result["failed_cases"])
    report_path = tmp_path / "output" / "benchmark" / "benchmark_report.json"
    failed_cases_path = tmp_path / "output" / "benchmark" / "runs" / result["run_id"] / "failed_cases.json"
    assert report_path.exists()
    assert failed_cases_path.exists()


def test_benchmark_cli_command_works(tmp_path: Path) -> None:
    _require_cadquery()

    result = main(["benchmark", "--output-root", str(tmp_path / "output")])

    assert result == 0
    assert (tmp_path / "output" / "benchmark" / "benchmark_report.json").exists()


def test_benchmark_cli_requires_cadquery(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_find_spec = cli.importlib.util.find_spec

    def fake_find_spec(name: str):
        if name == "cadquery":
            return None
        return real_find_spec(name)

    monkeypatch.setattr(cli.importlib.util, "find_spec", fake_find_spec)

    result = main(["benchmark"])

    output = capsys.readouterr().out
    assert result == 1
    assert "CadQuery is required to run `benchmark`" in output


def test_rejection_benchmark_cases_do_not_export_cad(tmp_path: Path) -> None:
    _require_cadquery()

    result = run_benchmark(output_root=tmp_path)
    rejection_results = [
        case
        for case in result["case_results"]
        if case["category"] == "rejections" or case["type"] == "parse"
    ]

    assert rejection_results
    for case in rejection_results:
        assert case["passed"] is True
        actual = case["actual"]
        assert actual["ok"] is False
        assert "step" not in actual
        assert "stl" not in actual
