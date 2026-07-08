"""Explicit edit aliases for wall-mounted bracket parameters.

Natural-language parsing is not implemented yet. These aliases only normalize
structured edit JSON keys into canonical parameter names used internally.
"""

PARAMETER_ALIASES: dict[str, str] = {
    "width": "back_plate_width_mm",
    "back_plate_width": "back_plate_width_mm",
    "back_plate_width_mm": "back_plate_width_mm",
    "height": "back_plate_height_mm",
    "back_plate_height": "back_plate_height_mm",
    "back_plate_height_mm": "back_plate_height_mm",
    "thickness": "back_plate_thickness_mm",
    "back_plate_thickness": "back_plate_thickness_mm",
    "back_plate_thickness_mm": "back_plate_thickness_mm",
    "hole_diameter": "mounting_hole_diameter_mm",
    "mounting_hole_diameter": "mounting_hole_diameter_mm",
    "mounting_hole_diameter_mm": "mounting_hole_diameter_mm",
    "hole_spacing": "mounting_hole_spacing_mm",
    "mounting_hole_spacing": "mounting_hole_spacing_mm",
    "mounting_hole_spacing_mm": "mounting_hole_spacing_mm",
    "hole_spacing_x": "mounting_hole_spacing_x_mm",
    "mounting_hole_spacing_x": "mounting_hole_spacing_x_mm",
    "mounting_hole_spacing_x_mm": "mounting_hole_spacing_x_mm",
    "hole_spacing_y": "mounting_hole_spacing_y_mm",
    "mounting_hole_spacing_y": "mounting_hole_spacing_y_mm",
    "mounting_hole_spacing_y_mm": "mounting_hole_spacing_y_mm",
    "hole_count": "mounting_hole_count",
    "mounting_hole_count": "mounting_hole_count",
    "cutout_width": "center_cutout_width_mm",
    "center_cutout_width": "center_cutout_width_mm",
    "center_cutout_width_mm": "center_cutout_width_mm",
    "cutout_height": "center_cutout_height_mm",
    "center_cutout_height": "center_cutout_height_mm",
    "center_cutout_height_mm": "center_cutout_height_mm",
    "corner_radius": "corner_radius_mm",
    "corner_radius_mm": "corner_radius_mm",
    "edge_fillet_radius": "fillet_radius_mm",
    "fillet_radius": "fillet_radius_mm",
    "fillet_radius_mm": "fillet_radius_mm",
}

INTENT_ALIASES: dict[str, str] = {
    "mounting_hole_symmetry": "mounting_hole_symmetry",
    "mounting_holes_symmetric": "mounting_hole_symmetry",
}


def canonical_parameter_name(name: str) -> str | None:
    """Return a canonical parameter name for a supported edit alias."""

    return PARAMETER_ALIASES.get(name)


def canonical_intent_name(name: str) -> str | None:
    """Return a canonical non-parameter intent name for a preserve alias."""

    return INTENT_ALIASES.get(name)
