from __future__ import annotations

import json
from pathlib import Path

from intentforge.cli import main
from intentforge.review import evaluate_assurance_case, get_review_policy
from tests.review_test_helpers import review_resources, standard_case


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    policy = get_review_policy("intentforge_standard_design_review_v1")
    decisions = [
        evaluate_assurance_case(policy, standard_case(), resources=review_resources()),
        evaluate_assurance_case(policy, standard_case(partial=True), resources=review_resources()),
        evaluate_assurance_case(policy, standard_case("l_bracket"), resources=review_resources()),
    ]
    paths = []
    for index, decision in enumerate(decisions):
        path = tmp_path / f"decision_{index}.json"
        path.write_text(decision.to_json(), encoding="utf-8")
        paths.append(path)
    return paths[0], paths[1], paths[2]


def test_diff_cli_renders_pairwise_markdown(capsys, tmp_path: Path) -> None:
    baseline, conditional, _ = _paths(tmp_path)
    assert main(["review", "diff", str(baseline), str(conditional)]) == 0
    output = capsys.readouterr().out
    assert "Differential Audit" in output
    assert "acceptance_constrained" in output


def test_diff_cli_returns_stable_json(capsys, tmp_path: Path) -> None:
    baseline, conditional, _ = _paths(tmp_path)
    assert main(["review", "diff", str(baseline), str(conditional), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision_transition"] == "acceptance_constrained"
    assert payload["deltas"]


def test_diff_cli_supports_multiple_variants_and_output_file(capsys, tmp_path: Path) -> None:
    baseline, conditional, l_variant = _paths(tmp_path)
    output = tmp_path / "multi_variant.md"
    assert main([
        "review", "diff", str(baseline), str(conditional), str(l_variant),
        "--output", str(output),
    ]) == 0
    assert output.is_file()
    assert "Multi-Variant" in output.read_text(encoding="utf-8")
    assert "Differential audit path" in capsys.readouterr().out
