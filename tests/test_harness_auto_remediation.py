"""Phase 30: Closed-loop QA harness tests for auto-remediation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.orchestrator import _auto_remediation_section


@pytest.fixture
def assurance_section() -> dict:
    return {"passed": True, "name": "assurance"}


def test_auto_remediation_section_runs_full_lifecycle(tmp_path: Path, assurance_section: dict) -> None:
    result = _auto_remediation_section(tmp_path, assurance_section)
    assert result["scenario_count"] == 2
    # Either every scenario was rejected initially (closed loop completes),
    # or the gate accepts a smaller subset. Both are valid as long as the
    # algebra synthetic step is deterministic.
    assert result["algebra_synthetic_status"] == "remediation_synthesized"
    assert result["passed"] is True
    assert result["final_dossier_built_count"] >= 1


def test_auto_remediation_section_writes_artifacts(tmp_path: Path, assurance_section: dict) -> None:
    result = _auto_remediation_section(tmp_path, assurance_section)
    report_path = Path(result["report_path"])
    assert report_path.is_file()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert "iterations" in payload
    assert any(item["step"] == "algebra_synthetic" for item in payload["iterations"])


def test_auto_remediation_section_is_deterministic(tmp_path: Path, assurance_section: dict) -> None:
    first = _auto_remediation_section(tmp_path / "first", assurance_section)
    second = _auto_remediation_section(tmp_path / "second", assurance_section)
    assert first["scenario_count"] == second["scenario_count"]
    assert first["iterations"] == second["iterations"]