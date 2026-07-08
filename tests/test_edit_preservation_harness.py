import json
from pathlib import Path

import pytest

from harness.edits import load_edit_chains, run_edit_chain, run_edit_preservation_harness
import intentforge.cli as cli
from intentforge.cli import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def test_edit_chains_load() -> None:
    chains = load_edit_chains()

    assert len(chains) >= 20
    assert all(chain["id"] for chain in chains)
    assert all(chain["initial_prompt"] for chain in chains)
    assert all(chain["edits"] for chain in chains)


def test_duplicate_chain_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "dup",
                    "object_type": "wall_mounted_bracket",
                    "initial_prompt": "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
                    "edits": [{"text": "Make it 150 mm wide.", "expected_changed": ["back_plate_width_mm"]}],
                },
                {
                    "id": "dup",
                    "object_type": "wall_mounted_bracket",
                    "initial_prompt": "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes.",
                    "edits": [{"text": "Make it 150 mm wide.", "expected_changed": ["back_plate_width_mm"]}],
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate chain id"):
        load_edit_chains(path)


def test_run_edit_chain_handles_accepted_edit() -> None:
    _require_cadquery()

    chain = next(chain for chain in load_edit_chains() if chain["id"] == "wall_edit_001")
    result = run_edit_chain(chain, export_enabled=False)

    assert result["passed"] is True
    assert result["step_count"] == 1
    assert result["steps"][0]["classification"] == "passed"
    changed = {item["canonical_parameter"] for item in result["steps"][0]["changed_parameters"]}
    preserved = {item["parameter"] for item in result["steps"][0]["preserved_parameters"]}
    assert "back_plate_width_mm" in changed
    assert "back_plate_thickness_mm" in preserved


def test_run_edit_chain_handles_expected_rejected_edit() -> None:
    _require_cadquery()

    chain = next(chain for chain in load_edit_chains() if chain["id"] == "reject_003")
    result = run_edit_chain(chain, export_enabled=False)

    assert result["passed"] is True
    assert result["steps"][0]["classification"] == "expected_rejection"
    assert result["steps"][0]["cad_exported"] is False


def test_edit_preservation_harness_writes_report(tmp_path: Path) -> None:
    _require_cadquery()

    result = run_edit_preservation_harness(tmp_path / "output", max_chains=3, export_enabled=False)

    report_path = Path(result["report_path"])
    summary_path = Path(result["summary_path"])
    persistent_dir = Path(result["persistent_output_dir"])
    assert report_path.exists()
    assert summary_path.exists()
    assert persistent_dir.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["run_id"] == result["run_id"]
    assert result["total_chains"] == 3


def test_cli_edit_harness_command_runs(capsys: pytest.CaptureFixture[str]) -> None:
    _require_cadquery()

    result = main(["edit-harness", "--max-chains", "2", "--no-export"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Edit preservation run:" in output
    assert "Report path:" in output
    assert (PROJECT_ROOT / "output" / "harness" / "edit_preservation_report.json").exists()


def test_cli_edit_harness_requires_cadquery(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    real_find_spec = cli.importlib.util.find_spec

    def fake_find_spec(name: str):
        if name == "cadquery":
            return None
        return real_find_spec(name)

    monkeypatch.setattr(cli.importlib.util, "find_spec", fake_find_spec)

    result = main(["edit-harness", "--max-chains", "1", "--no-export"])

    output = capsys.readouterr().out
    assert result == 1
    assert "CadQuery is required to run `edit-harness`" in output
