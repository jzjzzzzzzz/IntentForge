import json
from pathlib import Path

import pytest

from harness.sweeps import (
    generate_l_bracket_sweep_cases,
    generate_wall_bracket_sweep_cases,
    load_sweep_cases,
    run_parametric_sweep,
    run_sweep_case,
)
from intentforge.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def test_sweep_config_loads() -> None:
    config = load_sweep_cases()

    assert "wall_mounted_bracket" in config
    assert "l_bracket" in config
    assert config["wall_mounted_bracket"]["width"]
    assert config["l_bracket"]["base_leg_length"]


def test_generated_wall_bracket_cases_are_deterministic() -> None:
    config = load_sweep_cases()["wall_mounted_bracket"]

    first = generate_wall_bracket_sweep_cases(config, max_cases=12)
    second = generate_wall_bracket_sweep_cases(config, max_cases=12)

    assert first == second
    assert [case["id"] for case in first] == [case["id"] for case in second]


def test_generated_l_bracket_cases_are_deterministic() -> None:
    config = load_sweep_cases()["l_bracket"]

    first = generate_l_bracket_sweep_cases(config, max_cases=12)
    second = generate_l_bracket_sweep_cases(config, max_cases=12)

    assert first == second
    assert [case["id"] for case in first] == [case["id"] for case in second]


def test_each_generated_case_has_object_type() -> None:
    config = load_sweep_cases()
    cases = [
        *generate_wall_bracket_sweep_cases(config["wall_mounted_bracket"], max_cases=8),
        *generate_l_bracket_sweep_cases(config["l_bracket"], max_cases=8),
    ]

    assert cases
    assert all(case["object_type"] in {"wall_mounted_bracket", "l_bracket"} for case in cases)


def test_expected_invalid_case_classified_as_expected_rejection() -> None:
    config = load_sweep_cases()["wall_mounted_bracket"]
    invalid_case = generate_wall_bracket_sweep_cases(config, max_cases=1)[0]

    result = run_sweep_case(invalid_case)

    assert result["passed"] is True
    assert result["classification"] == "expected_rejection"


def test_unexpected_invalid_case_is_recorded_as_failed() -> None:
    config = load_sweep_cases()["wall_mounted_bracket"]
    invalid_case = generate_wall_bracket_sweep_cases(config, max_cases=1)[0]
    invalid_case = {**invalid_case, "expected_valid": True}

    result = run_sweep_case(invalid_case)

    assert result["passed"] is False
    assert result["classification"] == "generation_error"


def test_sweep_report_is_written(tmp_path: Path) -> None:
    _require_cadquery()

    result = run_parametric_sweep(tmp_path / "output", max_cases_per_family=4, export_enabled=False)

    report_path = Path(result["report_path"])
    summary_path = Path(result["summary_path"])
    assert result["total_cases"] == 8
    assert report_path.exists()
    assert summary_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["run_id"] == result["run_id"]
    assert report["families"]["wall_mounted_bracket"]["total"] == 4
    assert report["families"]["l_bracket"]["total"] == 4
    assert Path(result["output_paths"]["failed_cases"]).exists()
    assert Path(result["output_paths"]["passed_cases"]).exists()


def test_cli_sweep_command_runs_with_small_case_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _require_cadquery()
    monkeypatch.chdir(PROJECT_ROOT)

    result = main(["sweep", "--max-cases-per-family", "2", "--no-export"])

    assert result == 0
    assert (PROJECT_ROOT / "output" / "harness" / "sweep_report.json").exists()
