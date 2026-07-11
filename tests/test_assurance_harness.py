from pathlib import Path

import pytest

from harness.orchestrator import _assurance_section


def test_assurance_harness_section(tmp_path: Path) -> None:
    pytest.importorskip("cadquery")
    result = _assurance_section(tmp_path)
    assert result["passed"]
    assert result["assurance_fixture_count"] == 5
    assert result["deterministic_assurance_case_mismatch_count"] == 0
    assert result["deterministic_audit_package_mismatch_count"] == 0
