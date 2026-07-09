import json
from pathlib import Path

import pytest

from harness.adversarial import (
    load_adversarial_cases,
    run_adversarial_case,
    run_adversarial_harness,
    validate_adversarial_cases,
)
from intentforge.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_adversarial_prompts_load() -> None:
    cases = load_adversarial_cases()

    assert len(cases) >= 50
    assert all(case["id"] for case in cases)
    assert all(case["category"] for case in cases)
    assert all(case["mode"] for case in cases)


def test_duplicate_adversarial_ids_are_rejected() -> None:
    cases = load_adversarial_cases()
    duplicated = cases + [dict(cases[0])]

    with pytest.raises(ValueError, match="duplicate adversarial ids"):
        validate_adversarial_cases(duplicated)


def test_unsupported_object_case_rejects(tmp_path: Path) -> None:
    case = next(case for case in load_adversarial_cases() if case["id"] == "adv_001")

    result = run_adversarial_case(case, tmp_path)

    assert result["passed"] is True
    assert result["actual_ok"] is False
    assert result["cad_exported"] is False
    assert "Unsupported object" in result["actual_message"]


def test_vague_edit_rejects(tmp_path: Path) -> None:
    case = next(case for case in load_adversarial_cases() if case["id"] == "adv_029")

    result = run_adversarial_case(case, tmp_path)

    assert result["passed"] is True
    assert result["actual_ok"] is False
    assert result["cad_exported"] is False
    assert "measurable" in result["actual_message"]


def test_invalid_dimension_case_rejects_clearly(tmp_path: Path) -> None:
    case = next(case for case in load_adversarial_cases() if case["id"] == "adv_034")

    result = run_adversarial_case(case, tmp_path)

    assert result["passed"] is True
    assert "hole diameter" in result["actual_message"]
    assert result["cad_exported"] is False


def test_rejected_parse_build_does_not_export_cad(tmp_path: Path) -> None:
    case = next(case for case in load_adversarial_cases() if case["id"] == "adv_060")

    result = run_adversarial_case(case, tmp_path)

    assert result["passed"] is True
    assert result["cad_exported"] is False
    assert not list((tmp_path / "adv_060").rglob("*.step"))
    assert not list((tmp_path / "adv_060").rglob("*.stl"))


def test_adversarial_report_is_written(tmp_path: Path) -> None:
    result = run_adversarial_harness(tmp_path / "output", max_cases=8)

    report_path = Path(result["report_path"])
    summary_path = Path(result["summary_path"])
    persistent_dir = Path(result["persistent_output_dir"])
    assert result["total_cases"] == 8
    assert result["failed"] == 0
    assert report_path.exists()
    assert summary_path.exists()
    assert persistent_dir.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["run_id"] == result["run_id"]
    assert Path(result["output_paths"]["passed_cases"]).exists()
    assert Path(result["output_paths"]["failed_cases"]).exists()


def test_cli_adversarial_harness_runs_with_small_case_count(capsys: pytest.CaptureFixture[str]) -> None:
    result = main(["adversarial-harness", "--max-cases", "8"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Adversarial rejection run:" in output
    assert "Rejection success rate:" in output
    assert (PROJECT_ROOT / "output" / "harness" / "adversarial_report.json").exists()
