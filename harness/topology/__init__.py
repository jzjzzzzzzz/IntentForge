"""Topology inspection helpers for CadQuery/OpenCascade shapes."""

from harness.topology.shape_inspector import inspect_shape, write_shape_inspection_report
from harness.topology.volume_delta import (
    build_volume_delta_report,
    compare_volume_delta,
    estimate_l_bracket_base_hole_volume,
    estimate_l_bracket_gusset_volume,
    estimate_l_bracket_vertical_hole_volume,
    estimate_wall_bracket_cutout_volume,
    estimate_wall_bracket_hole_volume,
    make_volume_delta_check,
    volume_delta_checks_for_model,
    write_volume_delta_report,
)

__all__ = [
    "build_volume_delta_report",
    "compare_volume_delta",
    "estimate_l_bracket_base_hole_volume",
    "estimate_l_bracket_gusset_volume",
    "estimate_l_bracket_vertical_hole_volume",
    "estimate_wall_bracket_cutout_volume",
    "estimate_wall_bracket_hole_volume",
    "inspect_shape",
    "make_volume_delta_check",
    "volume_delta_checks_for_model",
    "write_shape_inspection_report",
    "write_volume_delta_report",
]
