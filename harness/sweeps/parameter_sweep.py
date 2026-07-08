"""Parametric sweep harness for supported IntentForge CAD families."""

from __future__ import annotations

from collections import Counter
from itertools import product
import json
from pathlib import Path
from typing import Any

import yaml

from harness.topology import build_volume_delta_report, inspect_shape
from intentforge.features import is_feature_active
from intentforge.generator.cadquery_generator import build_l_bracket, build_wall_bracket, export_model
from intentforge.output_manager import create_run_context, feature_state_names, json_safe_paths
from intentforge.schemas import ParameterTable, ValidationReport
from intentforge.validator.geometry_validator import validate_l_bracket, validate_wall_bracket

FAILURE_TYPES = (
    "expected_rejection",
    "generation_error",
    "validation_failure",
    "topology_failure",
    "volume_delta_failure",
    "unexpected_exception",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_config_path() -> Path:
    return Path(__file__).with_name("sweep_cases.yaml")


def load_sweep_cases(path: str | Path | None = None) -> dict[str, Any]:
    """Load sweep grid configuration from YAML."""

    config_path = Path(path) if path is not None else _default_config_path()
    with config_path.open("r", encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)
    return data or {}


def _parameter(
    name: str,
    value: int | float | str | bool,
    *,
    unit: str | None = None,
    description: str | None = None,
    reason: str | None = None,
    source: str = "user",
    min_value: float | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "description": description or f"Sweep parameter {name}.",
        "source": source,
        "reason": reason or "Included to exercise parametric sweep coverage.",
        "min_value": min_value,
    }


def _make_wall_flags(hole_pattern: str, center_cutout: bool, rounded_corners: bool, hole_count: int | None = None) -> dict[str, Any]:
    if hole_pattern == "none":
        mounting_holes = {
            "state": "omitted",
            "feature": "mounting_holes",
            "hole_count": 0,
            "pattern": "none",
            "reason": "Sweep case omits mounting holes.",
        }
    else:
        resolved_count = hole_count if hole_count is not None else (4 if hole_pattern == "rectangular_4" else 2)
        mounting_holes = {
            "state": "defaulted_by_system",
            "feature": "mounting_holes",
            "hole_count": resolved_count,
            "pattern": hole_pattern,
            "reason": f"Sweep case activates {hole_pattern} mounting holes.",
        }
    return {
        "mounting_holes": mounting_holes,
        "center_cutout": {
            "state": "defaulted_by_system" if center_cutout else "omitted",
            "reason": "Sweep case toggles center cutout.",
        },
        "rounded_corners": {
            "state": "defaulted_by_system" if rounded_corners else "omitted",
            "reason": "Sweep case toggles rounded corners.",
        },
        "edge_fillets": {
            "state": "omitted",
            "reason": "Sweep harness does not activate edge fillets.",
        },
    }


def _wall_parameter_table(
    *,
    width: float,
    height: float,
    thickness: float,
    hole_diameter: float,
    hole_pattern: str,
    center_cutout: bool,
    rounded_corners: bool,
    hole_count: int | None = None,
    cutout_width: float | None = None,
    cutout_height: float | None = None,
) -> dict[str, Any]:
    resolved_hole_count = hole_count if hole_count is not None else (0 if hole_pattern == "none" else 4 if hole_pattern == "rectangular_4" else 2)
    parameters = [
        _parameter("back_plate_width_mm", width, unit="mm", description="Overall wall bracket width.", min_value=1.0),
        _parameter("back_plate_height_mm", height, unit="mm", description="Overall wall bracket height.", min_value=1.0),
        _parameter("back_plate_thickness_mm", thickness, unit="mm", description="Wall bracket plate thickness.", min_value=1.0),
        _parameter("mounting_hole_count", resolved_hole_count, description="Mounting hole count.", min_value=0.0),
        _parameter("mounting_hole_diameter_mm", hole_diameter, unit="mm", description="Mounting hole diameter.", min_value=1.0),
    ]
    if hole_pattern == "rectangular_4":
        parameters.extend(
            [
                _parameter("mounting_hole_spacing_x_mm", width - 40, unit="mm", description="Four-hole X spacing.", source="derived", min_value=1.0),
                _parameter("mounting_hole_spacing_y_mm", height - 24, unit="mm", description="Four-hole Y spacing.", source="derived", min_value=1.0),
            ]
        )
    else:
        parameters.append(
            _parameter("mounting_hole_spacing_mm", width - 40, unit="mm", description="Two-hole horizontal spacing.", source="derived", min_value=1.0)
        )
    if center_cutout:
        parameters.extend(
            [
                _parameter("center_cutout_width_mm", cutout_width if cutout_width is not None else width * 0.30, unit="mm", description="Center cutout width.", source="derived", min_value=1.0),
                _parameter("center_cutout_height_mm", cutout_height if cutout_height is not None else height * 0.25, unit="mm", description="Center cutout height.", source="derived", min_value=1.0),
            ]
        )
    if rounded_corners:
        parameters.append(
            _parameter("corner_radius_mm", min(4.0, min(width, height) * 0.08), unit="mm", description="Rounded corner radius.", source="derived", min_value=0.0)
        )
    return {
        "family": "wall_mounted_bracket",
        "parameters": parameters,
        "assumptions": ["Parametric sweep generated this wall-mounted bracket case."],
        "unknowns": [],
        "metadata": {
            "min_edge_distance_mm": 3.0,
            "feature_flags": _make_wall_flags(hole_pattern, center_cutout, rounded_corners, resolved_hole_count),
            "sweep_case": True,
        },
    }


def _make_l_flags(base_holes: bool, vertical_holes: bool, gusset: bool, base_count: int = 2, vertical_count: int = 2) -> dict[str, Any]:
    return {
        "base_leg": {
            "state": "defaulted_by_system",
            "reason": "Base leg is required for the L-bracket family.",
        },
        "vertical_leg": {
            "state": "defaulted_by_system",
            "reason": "Vertical leg is required for the L-bracket family.",
        },
        "base_mounting_holes": {
            "state": "defaulted_by_system" if base_holes else "omitted",
            "feature": "base_mounting_holes",
            "hole_count": base_count if base_holes else 0,
            "pattern": "symmetric_2_horizontal" if base_holes and base_count == 2 else "none" if not base_holes else "unsupported",
            "reason": "Sweep case toggles base mounting holes.",
        },
        "vertical_mounting_holes": {
            "state": "defaulted_by_system" if vertical_holes else "omitted",
            "feature": "vertical_mounting_holes",
            "hole_count": vertical_count if vertical_holes else 0,
            "pattern": "symmetric_2_horizontal" if vertical_holes and vertical_count == 2 else "none" if not vertical_holes else "unsupported",
            "reason": "Sweep case toggles vertical mounting holes.",
        },
        "inside_fillet": {
            "state": "omitted",
            "reason": "Sweep harness does not activate inside fillets.",
        },
        "outside_edge_fillets": {
            "state": "omitted",
            "reason": "Sweep harness does not activate outside edge fillets.",
        },
        "triangular_gusset": {
            "state": "defaulted_by_system" if gusset else "omitted",
            "reason": "Sweep case toggles triangular gusset.",
        },
    }


def _l_parameter_table(
    *,
    base_leg_length: float,
    vertical_leg_length: float,
    bracket_width: float,
    thickness: float,
    base_holes: bool,
    vertical_holes: bool,
    gusset: bool,
    base_hole_count: int = 2,
    vertical_hole_count: int = 2,
    base_hole_spacing: float | None = None,
    vertical_hole_spacing: float | None = None,
    gusset_height: float | None = None,
) -> dict[str, Any]:
    parameters = [
        _parameter("base_leg_length_mm", base_leg_length, unit="mm", description="Horizontal L-bracket leg length.", min_value=1.0),
        _parameter("vertical_leg_length_mm", vertical_leg_length, unit="mm", description="Vertical L-bracket leg length.", min_value=1.0),
        _parameter("bracket_width_mm", bracket_width, unit="mm", description="Shared L-bracket width.", min_value=1.0),
        _parameter("thickness_mm", thickness, unit="mm", description="L-bracket material thickness.", min_value=1.0),
        _parameter("hole_diameter_mm", 5.0, unit="mm", description="L-bracket hole diameter.", min_value=1.0),
        _parameter("base_hole_count", base_hole_count if base_holes else 0, description="Base leg hole count.", min_value=0.0),
        _parameter("base_hole_spacing_mm", base_hole_spacing if base_hole_spacing is not None else base_leg_length - 40, unit="mm", description="Base leg hole spacing.", source="derived", min_value=1.0),
        _parameter("vertical_hole_count", vertical_hole_count if vertical_holes else 0, description="Vertical leg hole count.", min_value=0.0),
        _parameter("vertical_hole_spacing_mm", vertical_hole_spacing if vertical_hole_spacing is not None else vertical_leg_length - 30, unit="mm", description="Vertical leg hole spacing.", source="derived", min_value=1.0),
    ]
    if gusset:
        parameters.extend(
            [
                _parameter("gusset_enabled", True, description="Triangular gusset enabled flag.", source="derived"),
                _parameter("gusset_thickness_mm", min(8.0, bracket_width * 0.25), unit="mm", description="Triangular gusset thickness.", source="derived", min_value=1.0),
                _parameter("gusset_height_mm", gusset_height if gusset_height is not None else min(base_leg_length, vertical_leg_length) * 0.40, unit="mm", description="Triangular gusset height.", source="derived", min_value=1.0),
            ]
        )
    return {
        "family": "l_bracket",
        "parameters": parameters,
        "assumptions": ["Parametric sweep generated this L-bracket case."],
        "unknowns": [],
        "metadata": {
            "min_edge_distance_mm": 3.0,
            "feature_flags": _make_l_flags(base_holes, vertical_holes, gusset, base_hole_count, vertical_hole_count),
            "sweep_case": True,
        },
    }


def _sample_indices(total: int, target: int) -> list[int]:
    if total <= 0 or target <= 0:
        return []
    if total <= target:
        return list(range(total))
    step = total / target
    indices = [min(total - 1, int(index * step)) for index in range(target)]
    return sorted(dict.fromkeys(indices))


def _invalid_count(max_cases: int, available: int) -> int:
    if max_cases <= 0 or available <= 0:
        return 0
    return min(available, max(1, max_cases // 10))


def generate_wall_bracket_sweep_cases(config: dict[str, Any], max_cases: int = 100) -> list[dict[str, Any]]:
    """Generate deterministic sampled wall-mounted bracket sweep cases."""

    if max_cases <= 0:
        return []
    invalid_defs = config.get("invalid_cases", [])
    invalid_count = _invalid_count(max_cases, len(invalid_defs))
    valid_target = max_cases - invalid_count
    combos = list(
        product(
            config["width"],
            config["height"],
            config["thickness"],
            config["hole_diameter"],
            config["hole_pattern"],
            config["center_cutout"],
            config["rounded_corners"],
        )
    )
    cases: list[dict[str, Any]] = []
    for case_number, combo_index in enumerate(_sample_indices(len(combos), valid_target), start=1):
        width, height, thickness, hole_diameter, hole_pattern, center_cutout, rounded_corners = combos[combo_index]
        cases.append(
            {
                "id": f"wall_{case_number:03d}",
                "object_type": "wall_mounted_bracket",
                "expected_valid": True,
                "case_type": "valid",
                "parameters": {
                    "width": width,
                    "height": height,
                    "thickness": thickness,
                    "hole_diameter": hole_diameter,
                    "hole_pattern": hole_pattern,
                    "center_cutout": center_cutout,
                    "rounded_corners": rounded_corners,
                },
                "parameter_table": _wall_parameter_table(
                    width=float(width),
                    height=float(height),
                    thickness=float(thickness),
                    hole_diameter=float(hole_diameter),
                    hole_pattern=str(hole_pattern),
                    center_cutout=bool(center_cutout),
                    rounded_corners=bool(rounded_corners),
                ),
            }
        )

    for invalid in invalid_defs[:invalid_count]:
        name = invalid["name"]
        if name == "hole_diameter_too_large":
            table = _wall_parameter_table(
                width=80,
                height=40,
                thickness=6,
                hole_diameter=50,
                hole_pattern="symmetric_2_horizontal",
                center_cutout=False,
                rounded_corners=False,
            )
        elif name == "cutout_too_large":
            table = _wall_parameter_table(
                width=80,
                height=40,
                thickness=6,
                hole_diameter=5,
                hole_pattern="none",
                center_cutout=True,
                rounded_corners=False,
                cutout_width=90,
                cutout_height=45,
            )
        elif name == "unsupported_hole_count":
            table = _wall_parameter_table(
                width=100,
                height=60,
                thickness=6,
                hole_diameter=5,
                hole_pattern="unsupported",
                center_cutout=False,
                rounded_corners=False,
                hole_count=3,
            )
        else:
            continue
        cases.append(
            {
                "id": f"wall_invalid_{name}",
                "object_type": "wall_mounted_bracket",
                "expected_valid": False,
                "case_type": "invalid",
                "expected_rejection_reason": invalid.get("reason", name),
                "parameters": {"invalid_case": name},
                "parameter_table": table,
            }
        )
    return cases[:max_cases]


def generate_l_bracket_sweep_cases(config: dict[str, Any], max_cases: int = 100) -> list[dict[str, Any]]:
    """Generate deterministic sampled L-bracket sweep cases."""

    if max_cases <= 0:
        return []
    invalid_defs = config.get("invalid_cases", [])
    invalid_count = _invalid_count(max_cases, len(invalid_defs))
    valid_target = max_cases - invalid_count
    combos = list(
        product(
            config["base_leg_length"],
            config["vertical_leg_length"],
            config["bracket_width"],
            config["thickness"],
            config["base_holes"],
            config["vertical_holes"],
            config["gusset"],
        )
    )
    cases: list[dict[str, Any]] = []
    for case_number, combo_index in enumerate(_sample_indices(len(combos), valid_target), start=1):
        base_leg_length, vertical_leg_length, bracket_width, thickness, base_holes, vertical_holes, gusset = combos[combo_index]
        cases.append(
            {
                "id": f"l_bracket_{case_number:03d}",
                "object_type": "l_bracket",
                "expected_valid": True,
                "case_type": "valid",
                "parameters": {
                    "base_leg_length": base_leg_length,
                    "vertical_leg_length": vertical_leg_length,
                    "bracket_width": bracket_width,
                    "thickness": thickness,
                    "base_holes": base_holes,
                    "vertical_holes": vertical_holes,
                    "gusset": gusset,
                },
                "parameter_table": _l_parameter_table(
                    base_leg_length=float(base_leg_length),
                    vertical_leg_length=float(vertical_leg_length),
                    bracket_width=float(bracket_width),
                    thickness=float(thickness),
                    base_holes=bool(base_holes),
                    vertical_holes=bool(vertical_holes),
                    gusset=bool(gusset),
                ),
            }
        )

    for invalid in invalid_defs[:invalid_count]:
        name = invalid["name"]
        if name == "base_hole_spacing_too_large":
            table = _l_parameter_table(
                base_leg_length=80,
                vertical_leg_length=80,
                bracket_width=40,
                thickness=6,
                base_holes=True,
                vertical_holes=False,
                gusset=False,
                base_hole_spacing=78,
            )
        elif name == "unsupported_vertical_hole_count":
            table = _l_parameter_table(
                base_leg_length=100,
                vertical_leg_length=80,
                bracket_width=40,
                thickness=6,
                base_holes=False,
                vertical_holes=True,
                gusset=False,
                vertical_hole_count=3,
            )
        elif name == "gusset_too_large":
            table = _l_parameter_table(
                base_leg_length=80,
                vertical_leg_length=60,
                bracket_width=40,
                thickness=6,
                base_holes=False,
                vertical_holes=False,
                gusset=True,
                gusset_height=80,
            )
        else:
            continue
        cases.append(
            {
                "id": f"l_bracket_invalid_{name}",
                "object_type": "l_bracket",
                "expected_valid": False,
                "case_type": "invalid",
                "expected_rejection_reason": invalid.get("reason", name),
                "parameters": {"invalid_case": name},
                "parameter_table": table,
            }
        )
    return cases[:max_cases]


def _parameter_table_from_case(case: dict[str, Any]) -> ParameterTable:
    return ParameterTable.model_validate(case["parameter_table"])


def _build_model(parameter_table: ParameterTable) -> Any:
    if parameter_table.family == "l_bracket":
        return build_l_bracket(parameter_table)
    return build_wall_bracket(parameter_table)


def _validate_model(model: Any, parameter_table: ParameterTable) -> ValidationReport:
    if parameter_table.family == "l_bracket":
        return validate_l_bracket(model, parameter_table)
    return validate_wall_bracket(model, parameter_table)


def _topology_ok(topology_report: Any) -> bool:
    if topology_report.bounding_box_dimensions_mm is None:
        return False
    if topology_report.volume_mm3 is None:
        return False
    if topology_report.is_valid is False:
        return False
    return True


def _volume_delta_failed(validation_report: ValidationReport) -> bool:
    return any("volume_delta" in check.id and check.status == "fail" for check in validation_report.checks)


def _classify_validation_failure(validation_report: ValidationReport) -> str:
    if _volume_delta_failed(validation_report):
        return "volume_delta_failure"
    return "validation_failure"


def _case_cad_paths(case: dict[str, Any]) -> tuple[Path | None, Path | None]:
    output_dir = case.get("output_dir")
    if not output_dir:
        return None, None
    cad_dir = Path(output_dir) / case["object_type"]
    stem = case["id"]
    return cad_dir / f"{stem}.step", cad_dir / f"{stem}.stl"


def run_sweep_case(case: dict[str, Any]) -> dict[str, Any]:
    """Run generation, validation, topology inspection, and volume deltas for one sweep case."""

    expected_valid = bool(case.get("expected_valid", True))
    result: dict[str, Any] = {
        "id": case["id"],
        "object_type": case["object_type"],
        "expected_valid": expected_valid,
        "case_type": case.get("case_type", "valid"),
        "passed": False,
        "classification": "unexpected_exception",
        "failure_reason": "",
        "validation_valid": None,
        "topology_valid": None,
        "volume_delta_valid": None,
        "output_paths": {},
    }

    try:
        parameter_table = _parameter_table_from_case(case)
    except Exception as exc:
        result["classification"] = "unexpected_exception"
        result["failure_reason"] = f"Could not build parameter table: {exc}"
        return result

    try:
        model = _build_model(parameter_table)
    except ValueError as exc:
        if expected_valid:
            result["classification"] = "generation_error"
            result["failure_reason"] = str(exc)
            return result
        result.update(
            {
                "passed": True,
                "classification": "expected_rejection",
                "failure_reason": str(exc),
            }
        )
        return result
    except Exception as exc:  # pragma: no cover - CAD kernel failures vary
        result["classification"] = "unexpected_exception"
        result["failure_reason"] = str(exc)
        return result

    topology_report = inspect_shape(model, family=parameter_table.family)
    topology_valid = _topology_ok(topology_report)
    result["topology_valid"] = topology_valid

    validation_report = _validate_model(model, parameter_table)
    result["validation_valid"] = validation_report.valid
    volume_delta_records = validation_report.metadata.get("volume_delta_checks", [])
    result["volume_delta_valid"] = not any(record.get("status") == "fail" for record in volume_delta_records)
    result["validation_summary"] = validation_report.summary
    result["failed_validation_checks"] = [check.id for check in validation_report.failed_checks]
    result["topology"] = {
        "volume_mm3": topology_report.volume_mm3,
        "bounding_box_dimensions_mm": topology_report.bounding_box_dimensions_mm,
        "is_valid": topology_report.is_valid,
        "warnings": [warning.model_dump(mode="json") for warning in topology_report.warnings],
    }
    result["volume_delta_checks"] = volume_delta_records

    if not expected_valid:
        if not validation_report.valid:
            result.update(
                {
                    "passed": True,
                    "classification": "expected_rejection",
                    "failure_reason": "; ".join(result["failed_validation_checks"]),
                }
            )
        else:
            result.update(
                {
                    "classification": "validation_failure",
                    "failure_reason": "Expected invalid case built and validated successfully.",
                }
            )
        return result

    if not validation_report.valid:
        result["classification"] = _classify_validation_failure(validation_report)
        result["failure_reason"] = "; ".join(result["failed_validation_checks"])
        return result
    if not topology_valid:
        result["classification"] = "topology_failure"
        result["failure_reason"] = "Topology inspection did not return required bbox, volume, or validity metrics."
        return result

    if case.get("export_enabled", False):
        step_path, stl_path = _case_cad_paths(case)
        if step_path is not None and stl_path is not None:
            try:
                export_model(model, step_path, stl_path)
            except Exception as exc:  # pragma: no cover - exporter failures vary
                result["classification"] = "generation_error"
                result["failure_reason"] = f"CAD export failed: {exc}"
                return result
            result["output_paths"] = {
                "step": str(step_path),
                "stl": str(stl_path),
            }

    result.update(
        {
            "passed": True,
            "classification": "passed",
            "failure_reason": "",
        }
    )
    return result


def _summary_text(report: dict[str, Any]) -> str:
    lines = [
        f"Sweep run: {report['run_id']}",
        f"Total cases: {report['total_cases']}",
        f"Passed: {report['passed']}",
        f"Failed: {report['failed']}",
        f"Pass rate: {report['pass_rate']:.4f}",
        "Families:",
    ]
    for family, counts in report["families"].items():
        lines.append(f"  - {family}: passed {counts['passed']}, failed {counts['failed']}, total {counts['total']}")
    lines.append("Failure types:")
    for failure_type, count in report["failure_types"].items():
        lines.append(f"  - {failure_type}: {count}")
    if report["failed_cases"]:
        lines.append("Failed case IDs:")
        for case in report["failed_cases"]:
            lines.append(f"  - {case['id']}: {case['classification']} - {case['failure_reason']}")
    else:
        lines.append("Failed case IDs: none")
    return "\n".join(lines) + "\n"


def _write_json(data: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_text(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run_parametric_sweep(
    output_root: str | Path,
    max_cases_per_family: int = 100,
    *,
    export_enabled: bool = True,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run deterministic parametric sweeps for all supported model families."""

    output_path = Path(output_root)
    harness_root = output_path / "harness"
    run_context = create_run_context("parametric sweep", harness_root, "sweep_runs")
    config = load_sweep_cases(config_path)
    wall_cases = generate_wall_bracket_sweep_cases(config["wall_mounted_bracket"], max_cases=max_cases_per_family)
    l_cases = generate_l_bracket_sweep_cases(config["l_bracket"], max_cases=max_cases_per_family)

    results: list[dict[str, Any]] = []
    for case in [*wall_cases, *l_cases]:
        case = {
            **case,
            "export_enabled": export_enabled,
            "output_dir": str(run_context.run_dir / "cad"),
        }
        results.append(run_sweep_case(case))

    passed_cases = [result for result in results if result["passed"]]
    failed_cases = [result for result in results if not result["passed"]]
    families: dict[str, dict[str, int]] = {}
    for family in ("wall_mounted_bracket", "l_bracket"):
        family_results = [result for result in results if result["object_type"] == family]
        family_passed = sum(1 for result in family_results if result["passed"])
        families[family] = {
            "total": len(family_results),
            "passed": family_passed,
            "failed": len(family_results) - family_passed,
        }

    classification_counts = Counter(
        result["classification"]
        for result in results
        if result["classification"] != "passed"
    )
    failure_types = {failure_type: classification_counts.get(failure_type, 0) for failure_type in FAILURE_TYPES}

    total_cases = len(results)
    report: dict[str, Any] = {
        "run_id": run_context.run_id,
        "total_cases": total_cases,
        "passed": len(passed_cases),
        "failed": len(failed_cases),
        "pass_rate": len(passed_cases) / total_cases if total_cases else 0.0,
        "families": families,
        "failure_types": failure_types,
        "export_enabled": export_enabled,
        "failed_cases": failed_cases,
        "passed_cases": passed_cases,
    }

    latest_report_path = harness_root / "sweep_report.json"
    latest_summary_path = harness_root / "sweep_summary.txt"
    persistent_report_path = run_context.run_dir / "sweep_report.json"
    persistent_summary_path = run_context.run_dir / "sweep_summary.txt"
    failed_cases_path = run_context.run_dir / "failed_cases.json"
    passed_cases_path = run_context.run_dir / "passed_cases.json"
    output_paths = {
        "latest_report": latest_report_path,
        "latest_summary": latest_summary_path,
        "persistent_report": persistent_report_path,
        "persistent_summary": persistent_summary_path,
        "failed_cases": failed_cases_path,
        "passed_cases": passed_cases_path,
    }
    report["output_paths"] = json_safe_paths(output_paths)

    summary = _summary_text(report)
    _write_json(report, latest_report_path)
    _write_text(summary, latest_summary_path)
    _write_json(report, persistent_report_path)
    _write_text(summary, persistent_summary_path)
    _write_json(failed_cases, failed_cases_path)
    _write_json(passed_cases, passed_cases_path)

    return {
        **report,
        "report_path": str(latest_report_path),
        "summary_path": str(latest_summary_path),
        "persistent_output_dir": str(run_context.run_dir),
        "summary": summary,
    }
