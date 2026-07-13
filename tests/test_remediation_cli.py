"""Phase 30: CLI tests for the auto-remediation synthesis command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.phase27_test_helpers import build_three_package_chain


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "intentforge.cli", "review", *args],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "./src", "PATH": "/usr/bin:/bin"},
    )


def _write_parameters(package_dir, parameters):
    package_dir.joinpath("parameters.json").write_text(
        json.dumps(parameters, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def test_cli_synthesize_remediation_for_failed_package(tmp_path):
    chain = build_three_package_chain(tmp_path / "chain")
    package_dir = chain["packages"][0]
    _write_parameters(package_dir, {
        "back_plate_width_mm": 30.0,
        "back_plate_height_mm": 60.0,
        "back_plate_thickness_mm": 8.0,
        "mounting_hole_diameter_mm": 10.0,
        "mounting_hole_spacing_x_mm": 0.0,
        "mounting_hole_spacing_y_mm": 0.0,
    })
    proc = _run_cli("synthesize-remediation", str(package_dir), "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "remediation_synthesized"
    assert "delta" in payload


def test_cli_synthesize_remediation_text_output(tmp_path):
    chain = build_three_package_chain(tmp_path / "chain")
    package_dir = chain["packages"][0]
    _write_parameters(package_dir, {
        "back_plate_width_mm": 30.0,
        "back_plate_height_mm": 60.0,
        "back_plate_thickness_mm": 8.0,
        "mounting_hole_diameter_mm": 10.0,
        "mounting_hole_spacing_x_mm": 0.0,
        "mounting_hole_spacing_y_mm": 0.0,
    })
    proc = _run_cli("synthesize-remediation", str(package_dir))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "IntentForge Auto-Remediation Synthesis" in proc.stdout
    assert "Parameter changes:" in proc.stdout


def test_cli_synthesize_remediation_skips_clean_package(tmp_path):
    chain = build_three_package_chain(tmp_path / "chain")
    package_dir = chain["packages"][0]
    _write_parameters(package_dir, {
        "back_plate_width_mm": 120.0,
        "back_plate_height_mm": 60.0,
        "back_plate_thickness_mm": 8.0,
        "mounting_hole_diameter_mm": 6.0,
        "mounting_hole_spacing_x_mm": 60.0,
        "mounting_hole_spacing_y_mm": 30.0,
        "corner_radius_mm": 2.0,
    })
    proc = _run_cli("synthesize-remediation", str(package_dir), "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "skipped"


def test_cli_synthesize_remediation_with_parameters_override(tmp_path):
    chain = build_three_package_chain(tmp_path / "chain")
    package_dir = chain["packages"][0]
    override_path = tmp_path / "params.json"
    override_path.write_text(json.dumps({
        "back_plate_width_mm": 30.0,
        "back_plate_height_mm": 60.0,
        "back_plate_thickness_mm": 8.0,
        "mounting_hole_diameter_mm": 10.0,
        "mounting_hole_spacing_x_mm": 0.0,
    }, indent=2), encoding="utf-8")
    proc = _run_cli("synthesize-remediation", str(package_dir), "--parameters", str(override_path), "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["status"] == "remediation_synthesized"


def test_cli_synthesize_remediation_writes_to_output_dir(tmp_path):
    chain = build_three_package_chain(tmp_path / "chain")
    package_dir = chain["packages"][0]
    _write_parameters(package_dir, {
        "back_plate_width_mm": 30.0,
        "back_plate_height_mm": 60.0,
        "back_plate_thickness_mm": 8.0,
        "mounting_hole_diameter_mm": 10.0,
        "mounting_hole_spacing_x_mm": 0.0,
    })
    output_dir = tmp_path / "remediation"
    proc = _run_cli("synthesize-remediation", str(package_dir), "--output", str(output_dir), "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["remediation_path"].endswith("Remediation_Intent.json")
    assert Path(payload["remediation_path"]).is_file()