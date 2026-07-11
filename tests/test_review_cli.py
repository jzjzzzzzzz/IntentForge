from pathlib import Path

import pytest

from intentforge.cli import main


def test_policy_list_show_and_validate_cli(capsys) -> None:
    assert main(["review", "policies"]) == 0
    assert "Policies: 5" in capsys.readouterr().out
    assert main(["review", "policies", "--json"]) == 0
    assert main(["review", "policy-show", "intentforge_static_review_v1", "--json"]) == 0
    assert main(["review", "policy-validate"]) == 0


def test_build_evaluate_static_and_decision_commands(tmp_path: Path) -> None:
    assert main(["review", "build-evaluate", "--profile", "static", "--output-root", str(tmp_path)]) == 0
    decision = tmp_path / "review" / "review_decision.json"
    assert main(["review", "validate", str(decision)]) == 0
    assert main(["review", "show", str(decision), "--json"]) == 0
    assert main(["review", "render", str(decision), "--output", str(tmp_path / "decision.md")]) == 0
    assert main(["review", "compare", str(decision), str(decision), "--json"]) == 0


def test_partial_feature_returns_conditional_exit_code(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = main([
        "review", "build-evaluate", "--profile", "standard", "--dry-run",
        "--prompt", "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with rounded corners and two holes.",
        "--output-root", str(tmp_path / "output"),
    ])
    assert result == 2


def test_inside_fillet_returns_manual_review_exit_code(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = main([
        "review", "build-evaluate", "--profile", "standard", "--family", "l_bracket", "--dry-run",
        "--prompt", "Make an L-bracket 80 mm wide with 60 mm legs, two holes on each leg, and an inside fillet.",
        "--output-root", str(tmp_path / "output"),
    ])
    assert result == 3


def test_safe_rejection_cli_exit_zero_refers_to_handling(tmp_path: Path, capsys) -> None:
    result = main([
        "review", "build-evaluate", "--profile", "static",
        "--policy", "intentforge_safe_rejection_review_v1",
        "--prompt", "Make a gear with 24 teeth.", "--output-root", str(tmp_path),
    ])
    assert result == 0
    output = capsys.readouterr().out
    assert "unsupported design remains rejected" in output


def test_invalid_policy_returns_unresolved_input_exit(tmp_path: Path) -> None:
    assert main([
        "review", "build-evaluate", "--profile", "static", "--policy", "missing_policy",
        "--output-root", str(tmp_path),
    ]) == 5
