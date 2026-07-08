"""CadQuery generation for supported bracket families."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from intentforge.features import (
    feature_flags_for_parameter_table,
    is_feature_active,
    mounting_hole_count_from_flags,
    mounting_hole_pattern_from_flags,
)
from intentforge.schemas import FeaturePlan, ParameterTable

SUPPORTED_FAMILY = "wall_mounted_bracket"
L_BRACKET_FAMILY = "l_bracket"


class CadQueryUnavailableError(ImportError):
    """Raised when CadQuery-dependent behavior is requested without CadQuery."""


@dataclass(frozen=True)
class WallBracketDimensions:
    """Validated dimensions used by the wall-mounted bracket generator."""

    width: float
    height: float
    thickness: float
    mounting_hole_count: int
    mounting_hole_pattern: str
    mounting_hole_diameter: float | None
    mounting_hole_spacing_x: float | None
    mounting_hole_spacing_y: float | None
    center_cutout_width: float | None
    center_cutout_height: float | None
    corner_radius: float
    edge_fillet_radius: float | None
    feature_flags: dict[str, dict[str, str]]


@dataclass(frozen=True)
class LBracketDimensions:
    """Validated dimensions used by the L-bracket generator."""

    base_leg_length: float
    vertical_leg_length: float
    bracket_width: float
    thickness: float
    base_hole_count: int
    vertical_hole_count: int
    hole_diameter: float | None
    base_hole_spacing: float | None
    vertical_hole_spacing: float | None
    inside_fillet_radius: float | None
    outside_edge_fillet_radius: float | None
    gusset_enabled: bool
    gusset_thickness: float | None
    gusset_height: float | None
    feature_flags: dict[str, dict[str, str]]


def _import_cadquery() -> Any:
    try:
        import cadquery as cq
    except ImportError as exc:
        raise CadQueryUnavailableError(
            "CadQuery is required to build or export CAD models. "
            "Install it with: python -m pip install -e '.[cad]'"
        ) from exc
    return cq


def _numeric_parameter(parameter_table: ParameterTable, *names: str) -> float:
    for name in names:
        try:
            parameter = parameter_table.get(name)
        except KeyError:
            continue

        value = parameter.value
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{name} must be numeric")
        return float(value)

    joined = " or ".join(names)
    raise ValueError(f"missing required parameter: {joined}")


def _optional_numeric_parameter(parameter_table: ParameterTable, *names: str) -> float | None:
    try:
        return _numeric_parameter(parameter_table, *names)
    except ValueError as exc:
        if str(exc).startswith("missing required parameter"):
            return None
        raise


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} cannot be negative")


def _bool_parameter(parameter_table: ParameterTable, name: str, default: bool = False) -> bool:
    try:
        parameter = parameter_table.get(name)
    except KeyError:
        return default
    if not isinstance(parameter.value, bool):
        raise ValueError(f"{name} must be boolean")
    return parameter.value


def _wall_bracket_dimensions(parameter_table: ParameterTable) -> WallBracketDimensions:
    if parameter_table.family != SUPPORTED_FAMILY:
        raise ValueError(f"unsupported model family: {parameter_table.family}")

    feature_flags = feature_flags_for_parameter_table(parameter_table)
    mounting_holes_active = is_feature_active(feature_flags, "mounting_holes")
    center_cutout_active = is_feature_active(feature_flags, "center_cutout")
    rounded_corners_active = is_feature_active(feature_flags, "rounded_corners")
    edge_fillets_active = is_feature_active(feature_flags, "edge_fillets")

    dimensions = WallBracketDimensions(
        width=_numeric_parameter(parameter_table, "back_plate_width_mm"),
        height=_numeric_parameter(parameter_table, "back_plate_height_mm"),
        thickness=_numeric_parameter(parameter_table, "back_plate_thickness_mm"),
        mounting_hole_count=int(_optional_numeric_parameter(parameter_table, "mounting_hole_count") or mounting_hole_count_from_flags(feature_flags))
        if mounting_holes_active
        else 0,
        mounting_hole_pattern=mounting_hole_pattern_from_flags(feature_flags)
        if mounting_holes_active
        else "none",
        mounting_hole_diameter=_numeric_parameter(parameter_table, "mounting_hole_diameter_mm")
        if mounting_holes_active
        else None,
        mounting_hole_spacing_x=_numeric_parameter(
            parameter_table,
            "mounting_hole_spacing_x_mm",
            "mounting_hole_spacing_mm",
        )
        if mounting_holes_active
        else None,
        mounting_hole_spacing_y=_numeric_parameter(parameter_table, "mounting_hole_spacing_y_mm")
        if mounting_holes_active and mounting_hole_pattern_from_flags(feature_flags) == "rectangular_4"
        else None,
        center_cutout_width=_numeric_parameter(parameter_table, "center_cutout_width_mm", "cutout_width_mm")
        if center_cutout_active
        else None,
        center_cutout_height=_numeric_parameter(parameter_table, "center_cutout_height_mm", "cutout_height_mm")
        if center_cutout_active
        else None,
        corner_radius=_numeric_parameter(parameter_table, "corner_radius_mm")
        if rounded_corners_active
        else 0.0,
        edge_fillet_radius=_optional_numeric_parameter(parameter_table, "fillet_radius_mm", "edge_fillet_radius_mm")
        if edge_fillets_active
        else None,
        feature_flags=feature_flags,
    )

    positive_values = {
        "back_plate_width_mm": dimensions.width,
        "back_plate_height_mm": dimensions.height,
        "back_plate_thickness_mm": dimensions.thickness,
    }
    if mounting_holes_active:
        assert dimensions.mounting_hole_diameter is not None
        assert dimensions.mounting_hole_spacing_x is not None
        if dimensions.mounting_hole_count not in {2, 4}:
            raise ValueError("mounting_hole_count must be 2 or 4")
        expected_pattern = "rectangular_4" if dimensions.mounting_hole_count == 4 else "symmetric_2_horizontal"
        if dimensions.mounting_hole_pattern != expected_pattern:
            raise ValueError(
                f"mounting_hole pattern must be {expected_pattern} for count {dimensions.mounting_hole_count}"
            )
        positive_values["mounting_hole_diameter_mm"] = dimensions.mounting_hole_diameter
        positive_values["mounting_hole_spacing_x_mm"] = dimensions.mounting_hole_spacing_x
        if dimensions.mounting_hole_count == 4:
            if dimensions.mounting_hole_spacing_y is None:
                raise ValueError("missing required parameter: mounting_hole_spacing_y_mm")
            positive_values["mounting_hole_spacing_y_mm"] = dimensions.mounting_hole_spacing_y
    if center_cutout_active:
        assert dimensions.center_cutout_width is not None
        assert dimensions.center_cutout_height is not None
        positive_values["center_cutout_width_mm"] = dimensions.center_cutout_width
        positive_values["center_cutout_height_mm"] = dimensions.center_cutout_height
    for name, value in positive_values.items():
        _validate_positive(name, value)
    if rounded_corners_active:
        _validate_non_negative("corner_radius_mm", dimensions.corner_radius)
    if edge_fillets_active:
        if dimensions.edge_fillet_radius is None:
            raise ValueError("missing required parameter: fillet_radius_mm")
        _validate_non_negative("fillet_radius_mm", dimensions.edge_fillet_radius)

    if (
        mounting_holes_active
        and dimensions.mounting_hole_diameter is not None
        and dimensions.mounting_hole_diameter >= min(dimensions.width, dimensions.height)
    ):
        raise ValueError("mounting_hole_diameter_mm must be smaller than the plate dimensions")
    if (
        mounting_holes_active
        and dimensions.mounting_hole_diameter is not None
        and dimensions.mounting_hole_spacing_x is not None
        and dimensions.mounting_hole_spacing_x + dimensions.mounting_hole_diameter >= dimensions.width
    ):
        raise ValueError(
            "mounting_hole_spacing_x_mm plus mounting_hole_diameter_mm must fit within "
            "back_plate_width_mm"
        )
    if (
        mounting_holes_active
        and dimensions.mounting_hole_count == 4
        and dimensions.mounting_hole_spacing_y is not None
        and dimensions.mounting_hole_diameter is not None
        and dimensions.mounting_hole_spacing_y + dimensions.mounting_hole_diameter >= dimensions.height
    ):
        raise ValueError(
            "mounting_hole_spacing_y_mm plus mounting_hole_diameter_mm must fit within "
            "back_plate_height_mm"
        )
    if (
        center_cutout_active
        and dimensions.center_cutout_width is not None
        and dimensions.center_cutout_width >= dimensions.width
    ):
        raise ValueError("center_cutout_width_mm must be smaller than back_plate_width_mm")
    if (
        center_cutout_active
        and dimensions.center_cutout_height is not None
        and dimensions.center_cutout_height >= dimensions.height
    ):
        raise ValueError("center_cutout_height_mm must be smaller than back_plate_height_mm")
    if rounded_corners_active and dimensions.corner_radius * 2 >= min(dimensions.width, dimensions.height):
        raise ValueError("corner_radius_mm is too large for the back plate")
    if (
        edge_fillets_active
        and dimensions.edge_fillet_radius is not None
        and dimensions.edge_fillet_radius > dimensions.thickness / 2
    ):
        raise ValueError("fillet_radius_mm must be <= back_plate_thickness_mm / 2")

    return dimensions


def build_wall_bracket(parameter_table: ParameterTable):
    """Build a parametric wall-mounted bracket CadQuery model.

    The generated model always starts with a named-parameter back plate.
    Mounting holes, center cutout, rounded corners, and edge fillets are added
    only when their feature flags are active. All driving dimensions are read
    from the provided ParameterTable.
    """

    dimensions = _wall_bracket_dimensions(parameter_table)
    cq = _import_cadquery()
    feature_flags = dimensions.feature_flags
    mounting_holes_active = is_feature_active(feature_flags, "mounting_holes")
    center_cutout_active = is_feature_active(feature_flags, "center_cutout")
    rounded_corners_active = is_feature_active(feature_flags, "rounded_corners")
    edge_fillets_active = is_feature_active(feature_flags, "edge_fillets")

    profile = cq.Sketch().rect(dimensions.width, dimensions.height)
    if rounded_corners_active and dimensions.corner_radius > 0:
        profile = profile.vertices().fillet(dimensions.corner_radius)

    model = cq.Workplane("XY").placeSketch(profile).extrude(dimensions.thickness)

    if edge_fillets_active and dimensions.edge_fillet_radius and dimensions.edge_fillet_radius > 0:
        model = model.edges("|Z").fillet(dimensions.edge_fillet_radius)

    if mounting_holes_active:
        assert dimensions.mounting_hole_spacing_x is not None
        assert dimensions.mounting_hole_diameter is not None
        if dimensions.mounting_hole_count == 2:
            mounting_points = [
                (-dimensions.mounting_hole_spacing_x / 2, 0.0),
                (dimensions.mounting_hole_spacing_x / 2, 0.0),
            ]
        elif dimensions.mounting_hole_count == 4:
            assert dimensions.mounting_hole_spacing_y is not None
            mounting_points = [
                (-dimensions.mounting_hole_spacing_x / 2, -dimensions.mounting_hole_spacing_y / 2),
                (dimensions.mounting_hole_spacing_x / 2, -dimensions.mounting_hole_spacing_y / 2),
                (-dimensions.mounting_hole_spacing_x / 2, dimensions.mounting_hole_spacing_y / 2),
                (dimensions.mounting_hole_spacing_x / 2, dimensions.mounting_hole_spacing_y / 2),
            ]
        else:
            raise ValueError("mounting_hole_count must be 2 or 4")
        model = (
            model.faces(">Z")
            .workplane(centerOption="CenterOfBoundBox")
            .pushPoints(mounting_points)
            .hole(dimensions.mounting_hole_diameter)
        )

    if center_cutout_active:
        assert dimensions.center_cutout_width is not None
        assert dimensions.center_cutout_height is not None
        model = (
            model.faces(">Z")
            .workplane(centerOption="CenterOfBoundBox")
            .rect(dimensions.center_cutout_width, dimensions.center_cutout_height)
            .cutThruAll()
        )

    return model


def _l_bracket_dimensions(parameter_table: ParameterTable) -> LBracketDimensions:
    if parameter_table.family != L_BRACKET_FAMILY:
        raise ValueError(f"unsupported model family: {parameter_table.family}")

    feature_flags = feature_flags_for_parameter_table(parameter_table)
    base_holes_active = is_feature_active(feature_flags, "base_mounting_holes")
    vertical_holes_active = is_feature_active(feature_flags, "vertical_mounting_holes")
    inside_fillet_active = is_feature_active(feature_flags, "inside_fillet")
    outside_fillets_active = is_feature_active(feature_flags, "outside_edge_fillets")
    gusset_active = is_feature_active(feature_flags, "triangular_gusset")

    dimensions = LBracketDimensions(
        base_leg_length=_numeric_parameter(parameter_table, "base_leg_length_mm"),
        vertical_leg_length=_numeric_parameter(parameter_table, "vertical_leg_length_mm"),
        bracket_width=_numeric_parameter(parameter_table, "bracket_width_mm"),
        thickness=_numeric_parameter(parameter_table, "thickness_mm"),
        base_hole_count=int(_optional_numeric_parameter(parameter_table, "base_hole_count") or 0)
        if base_holes_active
        else 0,
        vertical_hole_count=int(_optional_numeric_parameter(parameter_table, "vertical_hole_count") or 0)
        if vertical_holes_active
        else 0,
        hole_diameter=_numeric_parameter(parameter_table, "hole_diameter_mm")
        if base_holes_active or vertical_holes_active
        else None,
        base_hole_spacing=_numeric_parameter(parameter_table, "base_hole_spacing_mm")
        if base_holes_active
        else None,
        vertical_hole_spacing=_numeric_parameter(parameter_table, "vertical_hole_spacing_mm")
        if vertical_holes_active
        else None,
        inside_fillet_radius=_numeric_parameter(parameter_table, "inside_fillet_radius_mm")
        if inside_fillet_active
        else None,
        outside_edge_fillet_radius=_numeric_parameter(parameter_table, "outside_edge_fillet_radius_mm")
        if outside_fillets_active
        else None,
        gusset_enabled=_bool_parameter(parameter_table, "gusset_enabled", gusset_active)
        if gusset_active
        else False,
        gusset_thickness=_numeric_parameter(parameter_table, "gusset_thickness_mm")
        if gusset_active
        else None,
        gusset_height=_numeric_parameter(parameter_table, "gusset_height_mm")
        if gusset_active
        else None,
        feature_flags=feature_flags,
    )

    for name, value in {
        "base_leg_length_mm": dimensions.base_leg_length,
        "vertical_leg_length_mm": dimensions.vertical_leg_length,
        "bracket_width_mm": dimensions.bracket_width,
        "thickness_mm": dimensions.thickness,
    }.items():
        _validate_positive(name, value)

    if dimensions.thickness >= min(dimensions.base_leg_length, dimensions.vertical_leg_length):
        raise ValueError("thickness_mm must be smaller than both L-bracket leg lengths")

    if base_holes_active:
        if dimensions.base_hole_count not in {0, 2}:
            raise ValueError("base_hole_count must be 0 or 2")
        if dimensions.base_hole_count == 2:
            assert dimensions.hole_diameter is not None and dimensions.base_hole_spacing is not None
            _validate_positive("hole_diameter_mm", dimensions.hole_diameter)
            _validate_positive("base_hole_spacing_mm", dimensions.base_hole_spacing)
            if dimensions.base_hole_spacing + dimensions.hole_diameter >= dimensions.base_leg_length:
                raise ValueError("base_hole_spacing_mm plus hole_diameter_mm must fit within base_leg_length_mm")

    if vertical_holes_active:
        if dimensions.vertical_hole_count not in {0, 2}:
            raise ValueError("vertical_hole_count must be 0 or 2")
        if dimensions.vertical_hole_count == 2:
            assert dimensions.hole_diameter is not None and dimensions.vertical_hole_spacing is not None
            _validate_positive("hole_diameter_mm", dimensions.hole_diameter)
            _validate_positive("vertical_hole_spacing_mm", dimensions.vertical_hole_spacing)
            if dimensions.vertical_hole_spacing + dimensions.hole_diameter >= dimensions.vertical_leg_length:
                raise ValueError(
                    "vertical_hole_spacing_mm plus hole_diameter_mm must fit within vertical_leg_length_mm"
                )

    if dimensions.hole_diameter is not None and dimensions.hole_diameter >= dimensions.bracket_width:
        raise ValueError("hole_diameter_mm must be smaller than bracket_width_mm")

    if inside_fillet_active:
        assert dimensions.inside_fillet_radius is not None
        _validate_non_negative("inside_fillet_radius_mm", dimensions.inside_fillet_radius)
        if dimensions.inside_fillet_radius > dimensions.thickness:
            raise ValueError("inside_fillet_radius_mm must be <= thickness_mm")
    if outside_fillets_active:
        assert dimensions.outside_edge_fillet_radius is not None
        _validate_non_negative("outside_edge_fillet_radius_mm", dimensions.outside_edge_fillet_radius)
        if dimensions.outside_edge_fillet_radius > dimensions.thickness / 2:
            raise ValueError("outside_edge_fillet_radius_mm must be <= thickness_mm / 2")
    if gusset_active:
        assert dimensions.gusset_thickness is not None and dimensions.gusset_height is not None
        _validate_positive("gusset_thickness_mm", dimensions.gusset_thickness)
        _validate_positive("gusset_height_mm", dimensions.gusset_height)
        if dimensions.gusset_thickness > dimensions.bracket_width:
            raise ValueError("gusset_thickness_mm must be <= bracket_width_mm")
        if dimensions.gusset_height >= min(dimensions.base_leg_length, dimensions.vertical_leg_length):
            raise ValueError("gusset_height_mm must be smaller than both L-bracket leg lengths")

    return dimensions


def build_l_bracket(parameter_table: ParameterTable, feature_plan: FeaturePlan | None = None):
    """Build a parametric L-bracket CadQuery model."""

    del feature_plan
    dimensions = _l_bracket_dimensions(parameter_table)
    cq = _import_cadquery()
    feature_flags = dimensions.feature_flags

    base_leg = cq.Workplane("XY").box(
        dimensions.base_leg_length,
        dimensions.bracket_width,
        dimensions.thickness,
        centered=(False, True, False),
    )
    vertical_leg = cq.Workplane("XY").box(
        dimensions.thickness,
        dimensions.bracket_width,
        dimensions.vertical_leg_length,
        centered=(False, True, False),
    )
    model = base_leg.union(vertical_leg)

    if is_feature_active(feature_flags, "base_mounting_holes") and dimensions.base_hole_count == 2:
        assert dimensions.base_hole_spacing is not None and dimensions.hole_diameter is not None
        base_hole_x = [
            dimensions.base_leg_length / 2 - dimensions.base_hole_spacing / 2,
            dimensions.base_leg_length / 2 + dimensions.base_hole_spacing / 2,
        ]
        for x_position in base_hole_x:
            cutter = (
                cq.Workplane("XY")
                .center(x_position, 0.0)
                .circle(dimensions.hole_diameter / 2)
                .extrude(dimensions.thickness + 2.0)
                .translate((0.0, 0.0, -1.0))
            )
            model = model.cut(cutter)

    if is_feature_active(feature_flags, "vertical_mounting_holes") and dimensions.vertical_hole_count == 2:
        assert dimensions.vertical_hole_spacing is not None and dimensions.hole_diameter is not None
        vertical_hole_z = [
            dimensions.vertical_leg_length / 2 - dimensions.vertical_hole_spacing / 2,
            dimensions.vertical_leg_length / 2 + dimensions.vertical_hole_spacing / 2,
        ]
        for z_position in vertical_hole_z:
            cutter = (
                cq.Workplane("YZ")
                .center(0.0, z_position)
                .circle(dimensions.hole_diameter / 2)
                .extrude(dimensions.thickness + 2.0)
                .translate((-1.0, 0.0, 0.0))
            )
            model = model.cut(cutter)

    if is_feature_active(feature_flags, "triangular_gusset") and dimensions.gusset_enabled:
        assert dimensions.gusset_thickness is not None and dimensions.gusset_height is not None
        gusset = (
            cq.Workplane("XZ")
            .polyline(
                [
                    (dimensions.thickness, dimensions.thickness),
                    (dimensions.gusset_height, dimensions.thickness),
                    (dimensions.thickness, dimensions.gusset_height),
                ]
            )
            .close()
            .extrude(dimensions.gusset_thickness)
            .translate((0.0, -dimensions.gusset_thickness / 2, 0.0))
        )
        model = model.union(gusset)

    if (
        is_feature_active(feature_flags, "outside_edge_fillets")
        and dimensions.outside_edge_fillet_radius is not None
        and dimensions.outside_edge_fillet_radius > 0
    ):
        model = model.edges().fillet(dimensions.outside_edge_fillet_radius)

    return model


def export_model(model: Any, step_path: str | Path, stl_path: str | Path) -> tuple[Path, Path]:
    """Export a CadQuery model to real STEP and STL files."""

    cq = _import_cadquery()
    step_output = Path(step_path)
    stl_output = Path(stl_path)
    step_output.parent.mkdir(parents=True, exist_ok=True)
    stl_output.parent.mkdir(parents=True, exist_ok=True)

    cq.exporters.export(model, str(step_output))
    cq.exporters.export(model, str(stl_output))

    for output_path in (step_output, stl_output):
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f"CadQuery export did not create a real file: {output_path}")

    return step_output, stl_output


def generate_cadquery_model(feature_plan: FeaturePlan, parameters: ParameterTable):
    """Backward-compatible wrapper for building a supported bracket model."""

    if feature_plan.family == SUPPORTED_FAMILY:
        return build_wall_bracket(parameters)
    if feature_plan.family == L_BRACKET_FAMILY:
        return build_l_bracket(parameters, feature_plan)
    raise ValueError(f"unsupported model family: {feature_plan.family}")
