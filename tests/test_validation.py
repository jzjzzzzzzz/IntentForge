import pytest
from pydantic import ValidationError

from intentforge.cli import main
from intentforge.schemas import ValidationCheck, ValidationReport


from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _require_cadquery() -> None:
    pytest.importorskip("cadquery")


def test_validation_report_passed_property_tracks_failures() -> None:
    report = ValidationReport(
        family="wall_mounted_bracket",
        checks=[
            ValidationCheck(
                id="back_plate_dimensions",
                description="Back plate dimensions match named parameters.",
                status="pass",
                related_parameters=["back_plate_width_mm", "back_plate_height_mm"],
            ),
            ValidationCheck(
                id="fillet_radius_within_thickness",
                description="Fillet radius is manufacturable.",
                status="warning",
                severity="warning",
                message="Fillet is close to the thickness limit.",
            ),
        ],
    )

    assert report.passed is True
    assert report.failed_checks == []

    failed_report = ValidationReport(
        family="wall_mounted_bracket",
        checks=[
            ValidationCheck(
                id="mounting_hole_count",
                description="Four mounting holes exist.",
                status="fail",
            )
        ],
    )

    assert failed_report.passed is False
    assert failed_report.failed_checks[0].id == "mounting_hole_count"


def test_validation_report_rejects_duplicate_check_ids() -> None:
    check = ValidationCheck(
        id="mounting_hole_count",
        description="Four mounting holes exist.",
        status="pass",
    )

    with pytest.raises(ValidationError):
        ValidationReport(family="wall_mounted_bracket", checks=[check, check])


def test_validate_example_writes_latest_and_persistent_reports() -> None:
    _require_cadquery()

    latest_report = PROJECT_ROOT / "output" / "validation_report.json"
    persistent_report = PROJECT_ROOT / "output" / "validation_reports" / "bracket_validation_report.json"
    if persistent_report.exists():
        persistent_report.unlink()

    result = main(["validate-example", "bracket"])

    assert result == 0
    assert latest_report.exists()
    assert persistent_report.exists()
