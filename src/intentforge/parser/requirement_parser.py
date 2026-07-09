"""Deterministic rule-based requirement parser for Phase 5.

This module intentionally does not call an LLM. It supports only simple
wall-mounted bracket prompts and converts them into the existing structured
schemas used by the generator and validators.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from intentforge.features import (
    hole_pattern_for_count,
    is_feature_active,
    make_feature_flag,
    make_mounting_hole_flag,
    mounting_hole_count_from_flags,
    mounting_hole_pattern_from_flags,
    normalize_feature_flags,
)
from intentforge.schemas import (
    Constraint,
    ConstraintGraph,
    FeaturePlan,
    FeatureStep,
    IntentSpec,
    Parameter,
    ParameterTable,
)

SUPPORTED_FAMILY = "wall_mounted_bracket"
L_BRACKET_FAMILY = "l_bracket"
DEFAULT_UNITS = "mm"
DEFAULT_WIDTH_MM = 120.0
DEFAULT_HEIGHT_MM = 60.0
DEFAULT_THICKNESS_MM = 8.0
DEFAULT_HOLE_COUNT = 2
DEFAULT_HOLE_DIAMETER_MM = 5.0
DEFAULT_CORNER_RADIUS_MM = 4.0
DEFAULT_EDGE_FILLET_RADIUS_MM = 1.5
DEFAULT_BASE_LEG_LENGTH_MM = 100.0
DEFAULT_VERTICAL_LEG_LENGTH_MM = 80.0
DEFAULT_BRACKET_WIDTH_MM = 40.0
DEFAULT_L_BRACKET_THICKNESS_MM = 6.0
MIN_EDGE_DISTANCE_MM = 3.0

UNSUPPORTED_OBJECTS = [
    "gear",
    "enclosure",
    "shaft coupler",
    "coupler",
    "hinge",
    "drone frame",
    "adjustable bracket",
]

VAGUE_PROMPT_PATTERNS = [
    r"\bmake it better\b",
    r"\bmake it stronger\b",
    r"\bmake it more beautiful\b",
    r"\bbeautiful\b",
    r"\boptimi[sz]e it\b",
    r"\boptimi[sz]e\b",
    r"\bmake it cheaper\b",
    r"\bcheaper\b",
]

INVALID_PROMPT_PATTERNS = [
    (
        r"\b(?:(?:add|use|make|with|to)\s+)?(?:three|3|five|5|six|6|seven|7|eight|8|nine|9|\d{2,})\s+"
        r"(?:screw\s+|mounting\s+|corner\s+)?holes?\b",
        "Invalid bracket constraint: unsupported hole counts are not supported.",
    ),
    (
        r"\bholes?\s+outside\s+(?:the\s+)?plate\b",
        "Invalid bracket constraint: holes must stay inside the plate.",
    ),
    (
        r"\b(?:freeform|arbitrary)\s+(?:screw\s+|mounting\s+)?holes?.*\b(?:coordinates|placement)\b",
        "Unsupported mounting hole pattern: freeform hole coordinates are not supported.",
    ),
    (
        r"\b(?:negative\s+thickness|thickness\s+negative)\b",
        "Invalid bracket constraint: thickness must be greater than zero.",
    ),
    (
        r"\b(?:sheet[-\s]?metal\s+)?flat\s+pattern\b",
        "Unsupported geometry for current phase: sheet-metal flat patterns are not supported.",
    ),
]


class UnsupportedObjectError(ValueError):
    """Raised when the prompt asks for an unsupported CAD object type."""


@dataclass(frozen=True)
class ParsedPrompt:
    """Structured parse result for a supported prompt."""

    intent: IntentSpec
    parameter_table: ParameterTable
    constraint_graph: ConstraintGraph
    feature_plan: FeaturePlan
    warnings: list[str]


def _normalise(prompt: str) -> str:
    text = prompt.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _has_supported_object(text: str) -> bool:
    return any(
        phrase in text
        for phrase in [
            "wall-mounted bracket",
            "wall mounted bracket",
            "bracket",
            "mounting plate",
            "mounting bracket",
        ]
    )


def _has_l_bracket_object(text: str) -> bool:
    return bool(
        re.search(r"\bl[-\s]?bracket\b", text)
        or re.search(r"\bright\s+angle\s+bracket\b", text)
        or re.search(r"\b90[-\s]?degree\s+bracket\b", text)
        or re.search(r"\bangle\s+bracket\b", text)
    )


def _reject_unsupported_if_needed(text: str) -> None:
    for pattern in VAGUE_PROMPT_PATTERNS:
        if re.search(pattern, text):
            raise UnsupportedObjectError(
                "Unsupported prompt for Phase 5. Please provide a measurable parameter or supported feature change."
            )

    for pattern, message in INVALID_PROMPT_PATTERNS:
        if re.search(pattern, text):
            raise UnsupportedObjectError(message)

    hole_vs_plate = re.search(
        r"\b(?:use|make|add)\s+(?P<hole>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\s+holes?\s+"
        r"(?:on|in)\s+a\s+(?P<plate>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\s+bracket\b",
        text,
    )
    if hole_vs_plate and float(hole_vs_plate.group("hole")) >= float(hole_vs_plate.group("plate")):
        raise UnsupportedObjectError(
            "Invalid bracket constraint: hole diameter must be smaller than the plate dimensions."
        )

    for object_name in UNSUPPORTED_OBJECTS:
        if re.search(rf"\b{re.escape(object_name)}s?\b", text):
            raise UnsupportedObjectError(
                "Unsupported object type for Phase 5. Currently only wall_mounted_bracket is supported."
            )

    if not _has_supported_object(text):
        raise UnsupportedObjectError(
            "Unsupported object type for Phase 5. Currently only wall_mounted_bracket is supported."
        )

    if re.search(
        r"\b(?:circular|diagonal|arbitrary)\s+(?:screw\s+|mounting\s+|corner\s+)?(?:holes?|hole\s+pattern|pattern|placement|coordinates)\b",
        text,
    ) or re.search(
        r"\b(?:circular|diagonal)\s+(?:hole\s+)?(?:pattern|placement|coordinates)\b",
        text,
    ):
        raise UnsupportedObjectError(
            "Unsupported mounting hole pattern for Phase 6.5. Supported patterns are none, two horizontal holes, and four rectangular holes."
        )


def _number(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group("value"))


def _dimension_value(text: str, canonical: str, aliases: list[str]) -> float | None:
    alias_group = "|".join(re.escape(alias) for alias in aliases)
    unit = r"(?:mm|millimeters?|millimetres?)?"
    patterns = [
        rf"\b(?:{alias_group})\s*(?:is|of|:)?\s*(?P<value>\d+(?:\.\d+)?)\s*{unit}\b",
        rf"\b(?P<value>\d+(?:\.\d+)?)\s*{unit}\s*(?:{alias_group})\b",
    ]
    for pattern in patterns:
        value = _number(pattern, text)
        if value is not None:
            return value

    if canonical == "hole_diameter":
        value = _number(
            r"\b(?P<value>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\s*(?:screw\s*)?holes?\b",
            text,
        )
        if value is not None:
            return value

    return None


def _hole_count(text: str) -> int | None:
    word_numbers = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
    }
    for word, value in word_numbers.items():
        if re.search(
            rf"\b{word}\s+(?:symmetric\s+|corner\s+)?(?:\d+(?:\.\d+)?\s*(?:mm|millimeters?|millimetres?)\s+)?"
            rf"(?:screw|mounting|corner)?\s*holes?\b",
            text,
        ):
            return value

    match = re.search(
        r"\b(?P<value>\d+)\s+(?:symmetric\s+|corner\s+)?"
        r"(?:(?:\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\s+)?"
        r"(?:screw|mounting|corner)?\s*holes?\b",
        text,
    )
    if match:
        return int(match.group("value"))
    return None


def _mentions_holes(text: str) -> bool:
    return bool(re.search(r"\b(?:screw|mounting)?\s*holes?\b", text))


def _mentions_no_holes(text: str) -> bool:
    return bool(re.search(r"\b(?:no|without)\s+(?:screw\s+|mounting\s+)?holes?\b", text))


def _mentions_corner_holes(text: str) -> bool:
    return bool(re.search(r"\b(?:four|4)\s+corner\s+(?:screw\s+|mounting\s+)?holes?\b", text))


def _mentions_rounded_corners(text: str) -> bool:
    return bool(re.search(r"\b(?:rounded|round|radiused)\s+corners?\b", text))


def _mentions_center_cutout(text: str) -> bool:
    return bool(
        re.search(r"\b(?:center|centre|middle|central)\s+(?:rectangular\s+)?(?:cutout|cut-out|opening)\b", text)
        or re.search(r"\brectangular\s+(?:center|centre|middle|central)?\s*(?:cutout|cut-out|opening)\b", text)
    )


def _mentions_edge_fillets(text: str) -> bool:
    return bool(re.search(r"\b(?:edge\s+)?fillets?\b", text))


def _hole_spacing_xy(text: str) -> tuple[float, float] | None:
    match = re.search(
        r"\b(?:four\s+holes\s+spaced|hole\s+spacing)\s+"
        r"(?P<x>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\s+by\s+"
        r"(?P<y>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\b",
        text,
    )
    if match:
        return float(match.group("x")), float(match.group("y"))

    match = re.search(
        r"\bhole\s+spacing\s+x\s*(?P<x>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)"
        r"\s+and\s+y\s*(?P<y>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\b",
        text,
    )
    if match:
        return float(match.group("x")), float(match.group("y"))

    return None


def _units(text: str, assumptions: list[str]) -> str:
    if re.search(r"\b(?:mm|millimeters?|millimetres?)\b", text):
        return "mm"
    assumptions.append("Units assumed to be millimeters.")
    return DEFAULT_UNITS


def _param(
    name: str,
    value: int | float,
    unit: str | None,
    description: str,
    source: str,
    reason: str,
    min_value: float | None = None,
) -> Parameter:
    return Parameter(
        name=name,
        value=value,
        unit=unit,
        description=description,
        source=source,
        reason=reason,
        min_value=min_value,
    )


def _build_parameter_table(
    values: dict[str, float | int],
    sources: dict[str, str],
    units: str,
    feature_flags: dict[str, dict[str, str]],
    assumptions: list[str],
    unknowns: list[str],
    warnings: list[str],
) -> ParameterTable:
    parameters = [
        _param(
            "back_plate_width_mm",
            values["width"],
            units,
            "Overall width of the wall back plate.",
            sources["width"],
            "Required to size the mounting face.",
            1.0,
        ),
        _param(
            "back_plate_height_mm",
            values["height"],
            units,
            "Overall height of the wall back plate.",
            sources["height"],
            "Required to size the mounting face.",
            1.0,
        ),
        _param(
            "back_plate_thickness_mm",
            values["thickness"],
            units,
            "Thickness of the back plate.",
            sources["thickness"],
            "Required for a stable wall interface.",
            1.0,
        ),
    ]
    if is_feature_active(feature_flags, "mounting_holes"):
        hole_count = int(values["hole_count"])
        hole_pattern = hole_pattern_for_count(hole_count) or "unsupported"
        parameters.extend(
            [
                _param(
                    "mounting_hole_count",
                    hole_count,
                    None,
                    "Number of mounting holes.",
                    sources["hole_count"],
                    f"Captures {hole_pattern} mounting-hole pattern intent.",
                    1.0,
                ),
                _param(
                    "mounting_hole_diameter_mm",
                    values["hole_diameter"],
                    units,
                    "Diameter of each mounting hole.",
                    sources["hole_diameter"],
                    "Controls screw clearance.",
                    1.0,
                ),
            ]
        )
        if hole_count == 2:
            parameters.append(
                _param(
                    "mounting_hole_spacing_mm",
                    values["hole_spacing"],
                    units,
                    "Center-to-center spacing between the two symmetric mounting holes.",
                    sources["hole_spacing"],
                    "Controls the symmetric horizontal wall fastener pattern.",
                    1.0,
                )
            )
        if hole_count == 4:
            parameters.extend(
                [
                    _param(
                        "mounting_hole_spacing_x_mm",
                        values["hole_spacing_x"],
                        units,
                        "Horizontal spacing between rectangular-pattern mounting holes.",
                        sources["hole_spacing_x"],
                        "Controls the rectangular four-hole pattern width.",
                        1.0,
                    ),
                    _param(
                        "mounting_hole_spacing_y_mm",
                        values["hole_spacing_y"],
                        units,
                        "Vertical spacing between rectangular-pattern mounting holes.",
                        sources["hole_spacing_y"],
                        "Controls the rectangular four-hole pattern height.",
                        1.0,
                    ),
                ]
            )
    if is_feature_active(feature_flags, "center_cutout"):
        parameters.extend(
            [
                _param(
                    "center_cutout_width_mm",
                    values["cutout_width"],
                    units,
                    "Width of the centered rectangular cutout.",
                    sources["cutout_width"],
                    "Creates an editable relief opening in the plate.",
                    1.0,
                ),
                _param(
                    "center_cutout_height_mm",
                    values["cutout_height"],
                    units,
                    "Height of the centered rectangular cutout.",
                    sources["cutout_height"],
                    "Creates an editable relief opening in the plate.",
                    1.0,
                ),
            ]
        )
    if is_feature_active(feature_flags, "rounded_corners"):
        parameters.append(
            _param(
                "corner_radius_mm",
                values["corner_radius"],
                units,
                "Outside corner radius for the back plate profile.",
                sources["corner_radius"],
                "Rounds the exposed outside plate corners robustly in the 2D profile.",
                0.0,
            )
        )
    if is_feature_active(feature_flags, "edge_fillets"):
        parameters.append(
            _param(
                "fillet_radius_mm",
                values["edge_fillet_radius"],
                units,
                "Exposed edge fillet radius.",
                sources["edge_fillet_radius"],
                "Captures edge-softening intent for validation and future modeling.",
                0.0,
            )
        )
    return ParameterTable(
        family=SUPPORTED_FAMILY,
        parameters=parameters,
        assumptions=assumptions,
        unknowns=unknowns,
        metadata={
            "parser": "rule_based_phase_5",
            "feature_flags": feature_flags,
            "warnings": warnings,
            "min_edge_distance_mm": MIN_EDGE_DISTANCE_MM,
        },
    )


def _build_intent(
    prompt: str,
    feature_flags: dict[str, dict[str, str]],
    assumptions: list[str],
    unknowns: list[str],
    warnings: list[str],
) -> IntentSpec:
    requirements = [
        "Back plate is rectangular.",
        "Important dimensions are named parameters.",
        "Feature history preserves modification intent.",
    ]
    if is_feature_active(feature_flags, "mounting_holes"):
        hole_pattern = mounting_hole_pattern_from_flags(feature_flags)
        if hole_pattern == "rectangular_4":
            requirements.append("Back plate has four rectangular-pattern mounting holes.")
        else:
            requirements.append("Back plate has two horizontal symmetric mounting holes.")
    if is_feature_active(feature_flags, "center_cutout"):
        requirements.append("Back plate has a centered rectangular cutout.")
    if is_feature_active(feature_flags, "rounded_corners"):
        requirements.append("Outside plate corners are rounded.")
    if is_feature_active(feature_flags, "edge_fillets"):
        requirements.append("Edge fillets are applied when valid.")

    return IntentSpec(
        family=SUPPORTED_FAMILY,
        user_prompt=prompt,
        objective="Generate an editable parametric wall-mounted bracket from a rule-parsed prompt.",
        requirements=requirements,
        assumptions=assumptions,
        unknowns=unknowns,
        metadata={"parser": "rule_based_phase_5", "warnings": warnings, "feature_flags": feature_flags},
    )


def _build_constraints(feature_flags: dict[str, dict[str, str]]) -> ConstraintGraph:
    nodes = [
        "back_plate_width_mm",
        "back_plate_height_mm",
        "back_plate_thickness_mm",
    ]
    dependencies: dict[str, list[str]] = {}
    constraints: list[Constraint] = []
    if is_feature_active(feature_flags, "mounting_holes"):
        hole_pattern = mounting_hole_pattern_from_flags(feature_flags)
        nodes.extend(["mounting_hole_count", "mounting_hole_diameter_mm"])
        if hole_pattern == "rectangular_4":
            nodes.extend(["mounting_hole_spacing_x_mm", "mounting_hole_spacing_y_mm"])
            dependencies["mounting_hole_spacing_x_mm"] = ["back_plate_width_mm", "mounting_hole_diameter_mm"]
            dependencies["mounting_hole_spacing_y_mm"] = ["back_plate_height_mm", "mounting_hole_diameter_mm"]
        else:
            nodes.append("mounting_hole_spacing_mm")
            dependencies["mounting_hole_spacing_mm"] = ["back_plate_width_mm", "mounting_hole_diameter_mm"]
        constraints.extend(
            [
                Constraint(
                    id="mounting_holes_symmetric",
                    kind="geometric",
                    expression=f"mounting_hole_pattern == {hole_pattern}",
                    parameters=["mounting_hole_count"],
                    reason="The mounting-hole pattern intent must remain explicit under edits.",
                ),
                Constraint(
                    id="hole_spacing_fits_plate",
                    kind="dimensional",
                    expression=(
                        "mounting_hole_spacing_x_mm / 2 + mounting_hole_diameter_mm / 2 "
                        "<= back_plate_width_mm / 2 - min_edge_distance_mm"
                        if hole_pattern == "rectangular_4"
                        else "mounting_hole_spacing_mm / 2 + mounting_hole_diameter_mm / 2 "
                        "<= back_plate_width_mm / 2 - min_edge_distance_mm"
                    ),
                    parameters=[
                        "mounting_hole_spacing_x_mm" if hole_pattern == "rectangular_4" else "mounting_hole_spacing_mm",
                        "mounting_hole_diameter_mm",
                        "back_plate_width_mm",
                    ],
                    reason="The mounting hole pattern must fit inside the plate width with edge clearance.",
                ),
            ]
        )
        if hole_pattern == "rectangular_4":
            constraints.append(
                Constraint(
                    id="hole_spacing_y_fits_plate",
                    kind="dimensional",
                    expression=(
                        "mounting_hole_spacing_y_mm / 2 + mounting_hole_diameter_mm / 2 "
                        "<= back_plate_height_mm / 2 - min_edge_distance_mm"
                    ),
                    parameters=[
                        "mounting_hole_spacing_y_mm",
                        "mounting_hole_diameter_mm",
                        "back_plate_height_mm",
                    ],
                    reason="The rectangular four-hole pattern must fit inside the plate height with edge clearance.",
                )
            )
    if is_feature_active(feature_flags, "center_cutout"):
        nodes.extend(["center_cutout_width_mm", "center_cutout_height_mm"])
        dependencies["center_cutout_width_mm"] = ["back_plate_width_mm"]
        dependencies["center_cutout_height_mm"] = ["back_plate_height_mm"]
        constraints.extend(
            [
                Constraint(
                    id="center_cutout_fits_plate_width",
                    kind="dimensional",
                    expression="center_cutout_width_mm < back_plate_width_mm - 2 * min_edge_distance_mm",
                    parameters=["center_cutout_width_mm", "back_plate_width_mm"],
                    reason="The center cutout must leave side material.",
                ),
                Constraint(
                    id="center_cutout_fits_plate_height",
                    kind="dimensional",
                    expression="center_cutout_height_mm < back_plate_height_mm - 2 * min_edge_distance_mm",
                    parameters=["center_cutout_height_mm", "back_plate_height_mm"],
                    reason="The center cutout must leave top and bottom material.",
                ),
            ]
        )
    if is_feature_active(feature_flags, "rounded_corners"):
        nodes.append("corner_radius_mm")
        dependencies["corner_radius_mm"] = ["back_plate_width_mm", "back_plate_height_mm"]
        constraints.append(
            Constraint(
                id="corner_radius_fits_plate",
                kind="geometric",
                expression="corner_radius_mm <= min(back_plate_width_mm, back_plate_height_mm) / 2",
                parameters=["corner_radius_mm", "back_plate_width_mm", "back_plate_height_mm"],
                reason="Rounded outside corners must fit inside the plate profile.",
            )
        )
    if is_feature_active(feature_flags, "edge_fillets"):
        nodes.append("fillet_radius_mm")
        dependencies["fillet_radius_mm"] = ["back_plate_thickness_mm"]
        constraints.append(
            Constraint(
                id="fillet_smaller_than_thickness",
                kind="manufacturing",
                expression="fillet_radius_mm <= back_plate_thickness_mm / 2",
                parameters=["fillet_radius_mm", "back_plate_thickness_mm"],
                reason="Fillets should remain smaller than half the available plate thickness.",
                severity="warning",
            )
        )
    return ConstraintGraph(
        family=SUPPORTED_FAMILY,
        nodes=nodes,
        dependencies=dependencies,
        constraints=constraints,
        assumptions=["Constraint expressions are recorded for deterministic validation."],
        unknowns=["No load or stress constraint is available yet."],
        metadata={
            "parser": "rule_based_phase_5",
            "feature_flags": feature_flags,
            "min_edge_distance_mm": MIN_EDGE_DISTANCE_MM,
        },
    )


def _build_feature_plan(feature_flags: dict[str, dict[str, str]]) -> FeaturePlan:
    steps = [
        FeatureStep(
            id="create_back_plate",
            operation="extrude_rounded_plate"
            if is_feature_active(feature_flags, "rounded_corners")
            else "extrude_plate",
            parameters=[
                "back_plate_width_mm",
                "back_plate_height_mm",
                "back_plate_thickness_mm",
            ]
            + (["corner_radius_mm"] if is_feature_active(feature_flags, "rounded_corners") else []),
            reason="The back plate is the wall mounting datum and base feature.",
            outputs=["back_plate_solid"],
            validation_refs=["back_plate_dimensions"],
        )
    ]
    if is_feature_active(feature_flags, "mounting_holes"):
        hole_pattern = mounting_hole_pattern_from_flags(feature_flags)
        parameters = ["mounting_hole_count", "mounting_hole_diameter_mm"]
        if hole_pattern == "rectangular_4":
            parameters.extend(["mounting_hole_spacing_x_mm", "mounting_hole_spacing_y_mm"])
        else:
            parameters.append("mounting_hole_spacing_mm")
        steps.append(
            FeatureStep(
                id="cut_mounting_holes",
                operation="cut_through_holes",
                parameters=parameters,
                depends_on=["create_back_plate"],
                reason=f"The bracket mounting-hole pattern is {hole_pattern}.",
                outputs=["mounting_holes"],
                validation_refs=["mounting_hole_count", "mounting_holes_symmetric"],
                metadata={"pattern": hole_pattern},
            )
        )
    if is_feature_active(feature_flags, "center_cutout"):
        steps.append(
            FeatureStep(
                id="cut_center_opening",
                operation="cut_center_rectangular_through_opening",
                parameters=["center_cutout_width_mm", "center_cutout_height_mm"],
                depends_on=["create_back_plate"],
                reason="The centered cutout creates an editable relief feature.",
                outputs=["center_cutout"],
                validation_refs=["center_cutout_fits_plate_width", "center_cutout_fits_plate_height"],
            )
        )
    if is_feature_active(feature_flags, "edge_fillets"):
        steps.append(
            FeatureStep(
                id="apply_edge_fillets",
                operation="fillet_exposed_edges",
                parameters=["fillet_radius_mm"],
                depends_on=[steps[-1].id],
                reason="Small edge fillets soften exposed edges when requested.",
                outputs=["edge_fillets"],
                validation_refs=["edge_fillet_limit_check"],
            )
        )
    return FeaturePlan(
        family=SUPPORTED_FAMILY,
        construction_strategy="Create a base plate, then add only requested or explicitly defaulted optional features.",
        steps=steps,
        assumptions=["Optional features are included only when active in feature_flags."],
        unknowns=["No load-bearing arm or gusset feature is added until load requirements are known."],
        metadata={"parser": "rule_based_phase_5", "feature_flags": feature_flags},
    )


def _add_default_assumption(assumptions: list[str], text: str) -> None:
    if text not in assumptions:
        assumptions.append(text)


def parse_bracket_prompt(prompt: str) -> ParsedPrompt:
    """Parse a simple wall-mounted bracket prompt with deterministic rules."""

    if not prompt or not prompt.strip():
        raise ValueError("prompt must not be empty")

    text = _normalise(prompt)
    _reject_unsupported_if_needed(text)

    assumptions: list[str] = []
    warnings: list[str] = []
    unknowns = [
        "material",
        "manufacturing method",
        "load requirement",
        "screw standard",
        "tolerance requirement",
    ]
    _add_default_assumption(assumptions, "Material was not specified.")
    _add_default_assumption(assumptions, "Load requirement was not specified.")

    units = _units(text, assumptions)
    no_holes_mentioned = _mentions_no_holes(text)
    holes_mentioned = _mentions_holes(text) and not no_holes_mentioned
    rounded_mentioned = _mentions_rounded_corners(text)
    cutout_mentioned = _mentions_center_cutout(text)
    edge_fillets_mentioned = _mentions_edge_fillets(text)
    requested_hole_count = _hole_count(text)
    if _mentions_corner_holes(text):
        requested_hole_count = 4
    if _hole_spacing_xy(text) is not None and requested_hole_count is None:
        requested_hole_count = 4
    if no_holes_mentioned:
        requested_hole_count = 0
    elif holes_mentioned and requested_hole_count is None:
        requested_hole_count = DEFAULT_HOLE_COUNT
    if requested_hole_count not in {None, 0, 2, 4}:
        raise UnsupportedObjectError(
            "Unsupported mounting hole pattern for Phase 6.5. Supported hole counts are 0, 2, and 4."
        )

    feature_flags = normalize_feature_flags(
        {
            "mounting_holes": make_mounting_hole_flag(
                "requested_by_user" if holes_mentioned else "omitted",
                "Prompt requested four mounting holes."
                if requested_hole_count == 4
                else "Prompt mentioned screw or mounting holes."
                if holes_mentioned
                else "Prompt explicitly omitted mounting holes."
                if no_holes_mentioned
                else "Prompt did not mention mounting holes.",
                requested_hole_count or 0,
            ),
            "center_cutout": make_feature_flag(
                "requested_by_user" if cutout_mentioned else "omitted",
                "Prompt mentioned a center cutout or central opening."
                if cutout_mentioned
                else "Prompt did not mention a center cutout.",
            ),
            "rounded_corners": make_feature_flag(
                "requested_by_user" if rounded_mentioned else "omitted",
                "Prompt mentioned rounded corners."
                if rounded_mentioned
                else "Prompt did not mention rounded corners.",
            ),
            "edge_fillets": make_feature_flag(
                "requested_by_user" if edge_fillets_mentioned else "omitted",
                "Prompt mentioned edge fillets."
                if edge_fillets_mentioned
                else "Prompt did not mention edge fillets.",
            ),
        }
    )
    if not holes_mentioned and not no_holes_mentioned:
        warnings.append("Mounting holes were not requested; generated plate will not include mounting holes.")

    extracted = {
        "width": _dimension_value(text, "width", ["wide", "width"]),
        "height": _dimension_value(text, "height", ["tall", "height", "high"]),
        "thickness": _dimension_value(text, "thickness", ["thick", "thickness"]),
        "hole_diameter": _dimension_value(text, "hole_diameter", ["hole diameter", "holes", "hole"]),
        "hole_spacing": _dimension_value(text, "hole_spacing", ["hole spacing", "spacing"]),
        "hole_spacing_xy": _hole_spacing_xy(text),
        "corner_radius": _dimension_value(text, "corner_radius", ["corner radius", "corner radii", "corner round"]),
        "cutout_width": _dimension_value(text, "cutout_width", ["cutout width", "opening width"]),
        "cutout_height": _dimension_value(text, "cutout_height", ["cutout height", "opening height"]),
        "edge_fillet_radius": _dimension_value(text, "edge_fillet_radius", ["edge fillet radius", "fillet radius"]),
    }
    if (
        holes_mentioned
        and extracted["hole_diameter"] is not None
        and (
            (extracted["width"] is not None and extracted["hole_diameter"] >= extracted["width"])
            or (extracted["height"] is not None and extracted["hole_diameter"] >= extracted["height"])
        )
    ):
        raise UnsupportedObjectError(
            "Invalid bracket constraint: hole diameter must be smaller than the plate dimensions."
        )

    values: dict[str, float | int] = {}
    sources: dict[str, str] = {}

    if extracted["width"] is None:
        values["width"] = DEFAULT_WIDTH_MM
        sources["width"] = "default"
        _add_default_assumption(assumptions, "Width defaulted to 120 mm.")
    else:
        values["width"] = extracted["width"]
        sources["width"] = "user"

    if extracted["height"] is None:
        values["height"] = DEFAULT_HEIGHT_MM
        sources["height"] = "default"
        _add_default_assumption(assumptions, "Height defaulted to 60 mm.")
    else:
        values["height"] = extracted["height"]
        sources["height"] = "user"

    if extracted["thickness"] is None:
        values["thickness"] = DEFAULT_THICKNESS_MM
        sources["thickness"] = "default"
        _add_default_assumption(assumptions, "Thickness defaulted to 8 mm.")
    else:
        values["thickness"] = extracted["thickness"]
        sources["thickness"] = "user"

    if is_feature_active(feature_flags, "mounting_holes"):
        hole_count = requested_hole_count
        if hole_count is None:
            values["hole_count"] = DEFAULT_HOLE_COUNT
            sources["hole_count"] = "default"
            _add_default_assumption(assumptions, "Hole count defaulted to 2.")
        else:
            values["hole_count"] = hole_count
            sources["hole_count"] = "user"

        if extracted["hole_diameter"] is None:
            values["hole_diameter"] = DEFAULT_HOLE_DIAMETER_MM
            sources["hole_diameter"] = "default"
            _add_default_assumption(assumptions, "Hole diameter defaulted to 5 mm.")
        else:
            values["hole_diameter"] = extracted["hole_diameter"]
            sources["hole_diameter"] = "user"

        if values["hole_count"] == 4:
            if extracted["hole_spacing_xy"] is None:
                values["hole_spacing_x"] = float(values["width"]) - 40.0
                values["hole_spacing_y"] = float(values["height"]) - 30.0
                sources["hole_spacing_x"] = "derived"
                sources["hole_spacing_y"] = "derived"
                _add_default_assumption(assumptions, "Hole spacing X defaulted to width - 40 mm.")
                _add_default_assumption(assumptions, "Hole spacing Y defaulted to height - 30 mm.")
            else:
                values["hole_spacing_x"], values["hole_spacing_y"] = extracted["hole_spacing_xy"]
                sources["hole_spacing_x"] = "user"
                sources["hole_spacing_y"] = "user"
        elif extracted["hole_spacing"] is None:
            values["hole_spacing"] = float(values["width"]) - 40.0
            sources["hole_spacing"] = "derived"
            _add_default_assumption(assumptions, "Hole spacing defaulted to width - 40 mm.")
        else:
            values["hole_spacing"] = extracted["hole_spacing"]
            sources["hole_spacing"] = "user"

    if is_feature_active(feature_flags, "rounded_corners"):
        if extracted["corner_radius"] is None:
            values["corner_radius"] = DEFAULT_CORNER_RADIUS_MM
            sources["corner_radius"] = "default"
            _add_default_assumption(assumptions, "Corner radius defaulted to 4 mm.")
        else:
            values["corner_radius"] = extracted["corner_radius"]
            sources["corner_radius"] = "user"

    if is_feature_active(feature_flags, "center_cutout"):
        if extracted["cutout_width"] is None:
            values["cutout_width"] = round(float(values["width"]) * 0.35, 3)
            sources["cutout_width"] = "derived"
            _add_default_assumption(assumptions, "Cutout width defaulted to width * 0.35.")
        else:
            values["cutout_width"] = extracted["cutout_width"]
            sources["cutout_width"] = "user"

        if extracted["cutout_height"] is None:
            values["cutout_height"] = round(float(values["height"]) * 0.30, 3)
            sources["cutout_height"] = "derived"
            _add_default_assumption(assumptions, "Cutout height defaulted to height * 0.30.")
        else:
            values["cutout_height"] = extracted["cutout_height"]
            sources["cutout_height"] = "user"

    if is_feature_active(feature_flags, "edge_fillets"):
        if extracted["edge_fillet_radius"] is None:
            values["edge_fillet_radius"] = DEFAULT_EDGE_FILLET_RADIUS_MM
            sources["edge_fillet_radius"] = "default"
            _add_default_assumption(assumptions, "Edge fillet radius defaulted to 1.5 mm.")
        else:
            values["edge_fillet_radius"] = extracted["edge_fillet_radius"]
            sources["edge_fillet_radius"] = "user"

    parameter_table = _build_parameter_table(
        values,
        sources,
        units,
        feature_flags,
        assumptions,
        unknowns,
        warnings,
    )
    intent = _build_intent(prompt, feature_flags, assumptions, unknowns, warnings)
    constraints = _build_constraints(feature_flags)
    feature_plan = _build_feature_plan(feature_flags)

    return ParsedPrompt(
        intent=intent,
        parameter_table=parameter_table,
        constraint_graph=constraints,
        feature_plan=feature_plan,
        warnings=warnings,
    )


def _reject_unsupported_l_bracket_prompt(text: str) -> None:
    if re.search(r"\b(?:curved|bend|bent)\s+l[-\s]?bracket\b", text):
        raise UnsupportedObjectError("Unsupported L-bracket request for Phase 10. Curved brackets are not supported.")
    if re.search(r"\badjustable\s+(?:l[-\s]?)?bracket\b", text):
        raise UnsupportedObjectError("Unsupported L-bracket request for Phase 10. Adjustable brackets are not supported.")
    if re.search(r"\b(?:sheet\s+metal\s+)?unfold|flat\s+pattern\b", text):
        raise UnsupportedObjectError("Unsupported L-bracket request for Phase 10. Sheet-metal unfold patterns are not supported.")
    if re.search(r"\b(?:freeform|arbitrary)\s+(?:hole\s+)?(?:placement|coordinates)\b", text):
        raise UnsupportedObjectError("Unsupported L-bracket request for Phase 10. Freeform hole placement is not supported.")
    if re.search(r"\b(?:three|3|four|4|five|5)\s+(?:holes?|mounting\s+holes?)\b", text):
        raise UnsupportedObjectError("Unsupported L-bracket hole pattern for Phase 10. Use 0 or 2 holes per leg.")


def _l_leg_holes_requested(text: str, leg: str) -> bool:
    if leg == "base":
        return bool(
            re.search(r"\b(?:two|2)\s+holes?\s+on\s+(?:the\s+)?base(?:\s+face|\s+leg)?\b", text)
            or re.search(r"\b(?:two|2)\s+base(?:\s+face|\s+leg)?\s+(?:mounting\s+|screw\s+)?holes?\b", text)
            or re.search(r"\bbase\s+face\s+(?:mounting\s+|screw\s+)?holes?\b", text)
            or re.search(r"\bbase\s+(?:mounting\s+|screw\s+)?holes?\b", text)
        )
    return bool(
        re.search(r"\b(?:two|2)\s+holes?\s+on\s+(?:the\s+)?(?:vertical|upright)(?:\s+face|\s+leg)?\b", text)
        or re.search(r"\b(?:two|2)\s+(?:vertical|upright)\s+(?:mounting\s+|screw\s+)?holes?\b", text)
        or re.search(r"\bvertical\s+face\s+(?:mounting\s+|screw\s+)?holes?\b", text)
        or re.search(r"\b(?:vertical|upright)\s+(?:mounting\s+|screw\s+)?holes?\b", text)
    )


def _l_holes_explicitly_omitted(text: str) -> bool:
    return bool(re.search(r"\b(?:plain\s+)?l[-\s]?bracket\s+with\s+no\s+holes\b", text) or _mentions_no_holes(text))


def _l_feature_flags(
    *,
    base_holes: bool,
    vertical_holes: bool,
    no_holes: bool,
    inside_fillet: bool,
    outside_fillets: bool,
    gusset: bool,
) -> dict[str, dict[str, Any]]:
    return normalize_feature_flags(
        {
            "base_leg": make_feature_flag(
                "defaulted_by_system",
                "Base leg is required for the L-bracket family.",
            ),
            "vertical_leg": make_feature_flag(
                "defaulted_by_system",
                "Vertical leg is required for the L-bracket family.",
            ),
            "base_mounting_holes": make_feature_flag(
                "requested_by_user" if base_holes else "omitted",
                "Prompt requested two holes on the base leg."
                if base_holes
                else "Prompt explicitly omitted holes."
                if no_holes
                else "Prompt did not mention base-leg holes.",
                feature="base_mounting_holes",
                hole_count=2 if base_holes else 0,
                pattern="symmetric_2_horizontal" if base_holes else "none",
            ),
            "vertical_mounting_holes": make_feature_flag(
                "requested_by_user" if vertical_holes else "omitted",
                "Prompt requested two holes on the vertical leg."
                if vertical_holes
                else "Prompt explicitly omitted holes."
                if no_holes
                else "Prompt did not mention vertical-leg holes.",
                feature="vertical_mounting_holes",
                hole_count=2 if vertical_holes else 0,
                pattern="symmetric_2_horizontal" if vertical_holes else "none",
            ),
            "inside_fillet": make_feature_flag(
                "requested_by_user" if inside_fillet else "omitted",
                "Prompt requested an inside fillet." if inside_fillet else "Prompt did not mention an inside fillet.",
            ),
            "outside_edge_fillets": make_feature_flag(
                "requested_by_user" if outside_fillets else "omitted",
                "Prompt requested outside edge fillets."
                if outside_fillets
                else "Prompt did not mention outside edge fillets.",
            ),
            "triangular_gusset": make_feature_flag(
                "requested_by_user" if gusset else "omitted",
                "Prompt requested a triangular gusset." if gusset else "Prompt did not mention a gusset.",
            ),
        },
        L_BRACKET_FAMILY,
    )


def _build_l_parameter_table(
    values: dict[str, float | int | bool],
    sources: dict[str, str],
    units: str,
    feature_flags: dict[str, dict[str, Any]],
    assumptions: list[str],
    unknowns: list[str],
    warnings: list[str],
) -> ParameterTable:
    parameters = [
        _param("base_leg_length_mm", values["base_leg_length"], units, "Length of the horizontal base leg.", sources["base_leg_length"], "Defines the horizontal mounting leg.", 1.0),
        _param("vertical_leg_length_mm", values["vertical_leg_length"], units, "Height of the vertical leg.", sources["vertical_leg_length"], "Defines the upright mounting leg.", 1.0),
        _param("bracket_width_mm", values["bracket_width"], units, "Width shared by both L-bracket legs.", sources["bracket_width"], "Controls the transverse bracket width.", 1.0),
        _param("thickness_mm", values["thickness"], units, "Plate thickness of both legs.", sources["thickness"], "Controls material thickness for both perpendicular plates.", 1.0),
    ]
    if is_feature_active(feature_flags, "base_mounting_holes") or is_feature_active(feature_flags, "vertical_mounting_holes"):
        parameters.append(
            _param("hole_diameter_mm", values["hole_diameter"], units, "Diameter of L-bracket mounting holes.", sources["hole_diameter"], "Controls screw clearance for active hole features.", 1.0)
        )
    if is_feature_active(feature_flags, "base_mounting_holes"):
        parameters.extend(
            [
                _param("base_hole_count", 2, None, "Number of base-leg mounting holes.", sources["base_hole_count"], "Phase 10 supports two symmetric holes on the base leg.", 0.0),
                _param("base_hole_spacing_mm", values["base_hole_spacing"], units, "Spacing between the two base-leg holes.", sources["base_hole_spacing"], "Controls symmetric base-leg hole placement.", 1.0),
            ]
        )
    if is_feature_active(feature_flags, "vertical_mounting_holes"):
        parameters.extend(
            [
                _param("vertical_hole_count", 2, None, "Number of vertical-leg mounting holes.", sources["vertical_hole_count"], "Phase 10 supports two symmetric holes on the vertical leg.", 0.0),
                _param("vertical_hole_spacing_mm", values["vertical_hole_spacing"], units, "Spacing between the two vertical-leg holes.", sources["vertical_hole_spacing"], "Controls symmetric vertical-leg hole placement.", 1.0),
            ]
        )
    if is_feature_active(feature_flags, "inside_fillet"):
        parameters.append(_param("inside_fillet_radius_mm", values["inside_fillet_radius"], units, "Inside corner fillet radius.", sources["inside_fillet_radius"], "Captures inside-corner radius intent.", 0.0))
    if is_feature_active(feature_flags, "outside_edge_fillets"):
        parameters.append(_param("outside_edge_fillet_radius_mm", values["outside_edge_fillet_radius"], units, "Outside exposed edge fillet radius.", sources["outside_edge_fillet_radius"], "Captures edge-softening intent.", 0.0))
    if is_feature_active(feature_flags, "triangular_gusset"):
        parameters.extend(
            [
                Parameter(name="gusset_enabled", value=bool(values["gusset_enabled"]), unit=None, description="Whether a triangular gusset is active.", source=sources["gusset_enabled"], reason="Controls the optional triangular reinforcement web."),
                _param("gusset_thickness_mm", values["gusset_thickness"], units, "Triangular gusset thickness across bracket width.", sources["gusset_thickness"], "Controls the optional gusset's transverse thickness.", 1.0),
                _param("gusset_height_mm", values["gusset_height"], units, "Triangular gusset leg height from the inside corner.", sources["gusset_height"], "Controls the optional gusset extent along both legs.", 1.0),
            ]
        )
    return ParameterTable(
        family=L_BRACKET_FAMILY,
        parameters=parameters,
        assumptions=assumptions,
        unknowns=unknowns,
        metadata={
            "parser": "rule_based_phase_10",
            "feature_flags": feature_flags,
            "warnings": warnings,
            "min_edge_distance_mm": MIN_EDGE_DISTANCE_MM,
        },
    )


def _build_l_intent(
    prompt: str,
    feature_flags: dict[str, dict[str, Any]],
    assumptions: list[str],
    unknowns: list[str],
    warnings: list[str],
) -> IntentSpec:
    requirements = [
        "L-bracket has two perpendicular rectangular legs joined at 90 degrees.",
        "Base and vertical leg dimensions are named parameters.",
        "Feature history preserves modification intent.",
    ]
    if is_feature_active(feature_flags, "base_mounting_holes"):
        requirements.append("Base leg has two symmetric mounting holes.")
    if is_feature_active(feature_flags, "vertical_mounting_holes"):
        requirements.append("Vertical leg has two symmetric mounting holes.")
    if is_feature_active(feature_flags, "triangular_gusset"):
        requirements.append("L-bracket includes a triangular gusset.")
    return IntentSpec(
        family=L_BRACKET_FAMILY,
        user_prompt=prompt,
        objective="Generate an editable parametric L-bracket from a rule-parsed prompt.",
        requirements=requirements,
        assumptions=assumptions,
        unknowns=unknowns,
        metadata={"parser": "rule_based_phase_10", "warnings": warnings, "feature_flags": feature_flags},
    )


def _build_l_constraints(feature_flags: dict[str, dict[str, Any]]) -> ConstraintGraph:
    nodes = ["base_leg_length_mm", "vertical_leg_length_mm", "bracket_width_mm", "thickness_mm"]
    dependencies: dict[str, list[str]] = {}
    constraints = [
        Constraint(
            id="l_bracket_right_angle",
            kind="geometric",
            expression="base_leg perpendicular_to vertical_leg",
            parameters=["base_leg_length_mm", "vertical_leg_length_mm", "thickness_mm"],
            reason="The L-bracket family is defined by a 90-degree inside corner.",
        )
    ]
    if is_feature_active(feature_flags, "base_mounting_holes") or is_feature_active(feature_flags, "vertical_mounting_holes"):
        nodes.append("hole_diameter_mm")
    if is_feature_active(feature_flags, "base_mounting_holes"):
        nodes.extend(["base_hole_count", "base_hole_spacing_mm"])
        dependencies["base_hole_spacing_mm"] = ["base_leg_length_mm", "hole_diameter_mm"]
        constraints.append(
            Constraint(
                id="base_holes_fit_leg",
                kind="dimensional",
                expression="base_hole_spacing_mm / 2 + hole_diameter_mm / 2 <= base_leg_length_mm / 2 - min_edge_distance_mm",
                parameters=["base_hole_spacing_mm", "hole_diameter_mm", "base_leg_length_mm"],
                reason="Base mounting holes must fit inside the horizontal leg.",
            )
        )
    if is_feature_active(feature_flags, "vertical_mounting_holes"):
        nodes.extend(["vertical_hole_count", "vertical_hole_spacing_mm"])
        dependencies["vertical_hole_spacing_mm"] = ["vertical_leg_length_mm", "hole_diameter_mm"]
        constraints.append(
            Constraint(
                id="vertical_holes_fit_leg",
                kind="dimensional",
                expression="vertical_hole_spacing_mm / 2 + hole_diameter_mm / 2 <= vertical_leg_length_mm / 2 - min_edge_distance_mm",
                parameters=["vertical_hole_spacing_mm", "hole_diameter_mm", "vertical_leg_length_mm"],
                reason="Vertical mounting holes must fit inside the upright leg.",
            )
        )
    if is_feature_active(feature_flags, "triangular_gusset"):
        nodes.extend(["gusset_enabled", "gusset_thickness_mm", "gusset_height_mm"])
        dependencies["gusset_height_mm"] = ["base_leg_length_mm", "vertical_leg_length_mm"]
        constraints.append(
            Constraint(
                id="gusset_fits_inside_corner",
                kind="geometric",
                expression="gusset_height_mm < min(base_leg_length_mm, vertical_leg_length_mm)",
                parameters=["gusset_height_mm", "base_leg_length_mm", "vertical_leg_length_mm"],
                reason="The triangular gusset must fit inside the L-bracket corner.",
            )
        )
    return ConstraintGraph(
        family=L_BRACKET_FAMILY,
        nodes=nodes,
        dependencies=dependencies,
        constraints=constraints,
        assumptions=["Constraint expressions are recorded for deterministic validation."],
        unknowns=["No load or stress constraint is available yet."],
        metadata={"parser": "rule_based_phase_10", "feature_flags": feature_flags, "min_edge_distance_mm": MIN_EDGE_DISTANCE_MM},
    )


def _build_l_feature_plan(feature_flags: dict[str, dict[str, Any]]) -> FeaturePlan:
    steps = [
        FeatureStep(id="create_base_leg", operation="extrude_base_leg", parameters=["base_leg_length_mm", "bracket_width_mm", "thickness_mm"], reason="The base leg is one required side of the L-bracket.", outputs=["base_leg_solid"], validation_refs=["base_leg_dimensions"]),
        FeatureStep(id="create_vertical_leg", operation="extrude_vertical_leg", parameters=["vertical_leg_length_mm", "bracket_width_mm", "thickness_mm"], reason="The vertical leg is the perpendicular side of the L-bracket.", outputs=["vertical_leg_solid"], validation_refs=["vertical_leg_dimensions"]),
        FeatureStep(id="join_legs_at_right_angle", operation="boolean_union", parameters=["thickness_mm"], depends_on=["create_base_leg", "create_vertical_leg"], reason="The two plates must share a 90-degree inside corner.", outputs=["l_bracket_solid"], validation_refs=["l_bracket_right_angle"]),
    ]
    if is_feature_active(feature_flags, "base_mounting_holes"):
        steps.append(FeatureStep(id="cut_base_mounting_holes", operation="cut_two_base_holes", parameters=["base_hole_count", "hole_diameter_mm", "base_hole_spacing_mm"], depends_on=["join_legs_at_right_angle"], reason="Base leg mounting holes were requested.", outputs=["base_mounting_holes"], validation_refs=["base_holes_fit_leg"], metadata={"pattern": "symmetric_2_horizontal"}))
    if is_feature_active(feature_flags, "vertical_mounting_holes"):
        steps.append(FeatureStep(id="cut_vertical_mounting_holes", operation="cut_two_vertical_holes", parameters=["vertical_hole_count", "hole_diameter_mm", "vertical_hole_spacing_mm"], depends_on=["join_legs_at_right_angle"], reason="Vertical leg mounting holes were requested.", outputs=["vertical_mounting_holes"], validation_refs=["vertical_holes_fit_leg"], metadata={"pattern": "symmetric_2_horizontal"}))
    if is_feature_active(feature_flags, "triangular_gusset"):
        steps.append(FeatureStep(id="add_triangular_gusset", operation="add_triangular_gusset", parameters=["gusset_enabled", "gusset_thickness_mm", "gusset_height_mm"], depends_on=["join_legs_at_right_angle"], reason="A triangular gusset was requested for reinforcement intent.", outputs=["triangular_gusset"], validation_refs=["gusset_fits_inside_corner"]))
    if is_feature_active(feature_flags, "inside_fillet"):
        steps.append(FeatureStep(id="add_inside_fillet", operation="fillet_inside_corner", parameters=["inside_fillet_radius_mm"], depends_on=[steps[-1].id], reason="Inside corner radius intent was requested.", outputs=["inside_fillet"], validation_refs=["inside_fillet_limit_check"]))
    if is_feature_active(feature_flags, "outside_edge_fillets"):
        steps.append(FeatureStep(id="add_outside_edge_fillets", operation="fillet_exposed_edges", parameters=["outside_edge_fillet_radius_mm"], depends_on=[steps[-1].id], reason="Outside edge fillet intent was requested.", outputs=["outside_edge_fillets"], validation_refs=["outside_edge_fillet_limit_check"]))
    return FeaturePlan(
        family=L_BRACKET_FAMILY,
        construction_strategy="Create perpendicular legs, union them, cut requested holes, then add optional reinforcement and fillets.",
        steps=steps,
        assumptions=["Only 0 or 2 holes per leg are supported in Phase 10."],
        unknowns=["No sheet-metal unfold pattern or load rating is generated."],
        metadata={"parser": "rule_based_phase_10", "feature_flags": feature_flags},
    )


def parse_l_bracket_prompt(prompt: str) -> ParsedPrompt:
    """Parse a simple L-bracket prompt with deterministic rules."""

    if not prompt or not prompt.strip():
        raise ValueError("prompt must not be empty")

    text = _normalise(prompt)
    for pattern in VAGUE_PROMPT_PATTERNS:
        if re.search(pattern, text):
            raise UnsupportedObjectError(
                "Unsupported prompt for Phase 10. Please provide measurable L-bracket parameters or supported features."
            )
    if not _has_l_bracket_object(text):
        raise UnsupportedObjectError("Unsupported object type for Phase 10. Currently l_bracket parsing requires an L-bracket prompt.")
    _reject_unsupported_l_bracket_prompt(text)

    assumptions: list[str] = []
    warnings: list[str] = []
    unknowns = ["material", "manufacturing method", "load requirement", "screw standard", "tolerance requirement"]
    _add_default_assumption(assumptions, "Material was not specified.")
    _add_default_assumption(assumptions, "Load requirement was not specified.")
    units = _units(text, assumptions)

    no_holes = _l_holes_explicitly_omitted(text)
    base_holes = _l_leg_holes_requested(text, "base") and not no_holes
    vertical_holes = _l_leg_holes_requested(text, "vertical") and not no_holes
    if "with two holes" in text and "base" not in text and "vertical" not in text and "upright" not in text:
        warnings.append("Two holes were mentioned without a leg; L-bracket holes were omitted because the target leg was unclear.")
    inside_fillet = bool(re.search(r"\binside\s+fillet\b|\binside\s+radius\b", text))
    outside_fillets = bool(re.search(r"\boutside\s+(?:edge\s+)?fillets?\b|\bedge\s+fillets?\b", text))
    gusset = bool(re.search(r"\b(?:triangular\s+)?gusset\b", text))
    feature_flags = _l_feature_flags(
        base_holes=base_holes,
        vertical_holes=vertical_holes,
        no_holes=no_holes,
        inside_fillet=inside_fillet,
        outside_fillets=outside_fillets,
        gusset=gusset,
    )
    if not base_holes and not vertical_holes and not no_holes:
        warnings.append("Mounting holes were not requested for either L-bracket leg; generated L-bracket will not include holes.")

    extracted = {
        "base_leg_length": _dimension_value(text, "base_leg_length", ["base leg", "base"]),
        "vertical_leg_length": _dimension_value(text, "vertical_leg_length", ["vertical leg", "vertical", "upright"]),
        "bracket_width": _dimension_value(text, "bracket_width", ["bracket width", "width", "wide"]),
        "thickness": _dimension_value(text, "thickness", ["thick", "thickness"]),
        "hole_diameter": _dimension_value(text, "hole_diameter", ["hole diameter", "holes", "hole"]),
        "base_hole_spacing": _dimension_value(text, "base_hole_spacing", ["base hole spacing"]),
        "vertical_hole_spacing": _dimension_value(text, "vertical_hole_spacing", ["vertical hole spacing"]),
        "inside_fillet_radius": _dimension_value(text, "inside_fillet_radius", ["inside fillet radius", "inside radius"]),
        "outside_edge_fillet_radius": _dimension_value(text, "outside_edge_fillet_radius", ["outside edge fillet radius", "outside fillet radius"]),
    }

    values: dict[str, float | int | bool] = {}
    sources: dict[str, str] = {}
    defaults = {
        "base_leg_length": (DEFAULT_BASE_LEG_LENGTH_MM, "Base leg length defaulted to 100 mm."),
        "vertical_leg_length": (DEFAULT_VERTICAL_LEG_LENGTH_MM, "Vertical leg length defaulted to 80 mm."),
        "bracket_width": (DEFAULT_BRACKET_WIDTH_MM, "Bracket width defaulted to 40 mm."),
        "thickness": (DEFAULT_L_BRACKET_THICKNESS_MM, "Thickness defaulted to 6 mm."),
    }
    for key, (default_value, assumption) in defaults.items():
        if extracted[key] is None:
            values[key] = default_value
            sources[key] = "default"
            _add_default_assumption(assumptions, assumption)
        else:
            values[key] = extracted[key]
            sources[key] = "user"

    if base_holes or vertical_holes:
        values["hole_diameter"] = extracted["hole_diameter"] or DEFAULT_HOLE_DIAMETER_MM
        sources["hole_diameter"] = "user" if extracted["hole_diameter"] is not None else "default"
        if extracted["hole_diameter"] is None:
            _add_default_assumption(assumptions, "Hole diameter defaulted to 5 mm.")
    if base_holes:
        values["base_hole_spacing"] = extracted["base_hole_spacing"] or float(values["base_leg_length"]) - 40.0
        values["base_hole_count"] = 2
        sources["base_hole_spacing"] = "user" if extracted["base_hole_spacing"] is not None else "derived"
        sources["base_hole_count"] = "user"
        if extracted["base_hole_spacing"] is None:
            _add_default_assumption(assumptions, "Base hole spacing defaulted to base_leg_length - 40 mm.")
    if vertical_holes:
        values["vertical_hole_spacing"] = extracted["vertical_hole_spacing"] or float(values["vertical_leg_length"]) - 40.0
        values["vertical_hole_count"] = 2
        sources["vertical_hole_spacing"] = "user" if extracted["vertical_hole_spacing"] is not None else "derived"
        sources["vertical_hole_count"] = "user"
        if extracted["vertical_hole_spacing"] is None:
            _add_default_assumption(assumptions, "Vertical hole spacing defaulted to vertical_leg_length - 40 mm.")
    if inside_fillet:
        values["inside_fillet_radius"] = extracted["inside_fillet_radius"] or 3.0
        sources["inside_fillet_radius"] = "user" if extracted["inside_fillet_radius"] is not None else "default"
        if extracted["inside_fillet_radius"] is None:
            _add_default_assumption(assumptions, "Inside fillet radius defaulted to 3 mm.")
    if outside_fillets:
        values["outside_edge_fillet_radius"] = extracted["outside_edge_fillet_radius"] or 1.0
        sources["outside_edge_fillet_radius"] = "user" if extracted["outside_edge_fillet_radius"] is not None else "default"
        if extracted["outside_edge_fillet_radius"] is None:
            _add_default_assumption(assumptions, "Outside edge fillet radius defaulted to 1 mm.")
    if gusset:
        values["gusset_enabled"] = True
        values["gusset_thickness"] = float(values["thickness"])
        values["gusset_height"] = round(min(float(values["base_leg_length"]), float(values["vertical_leg_length"])) * 0.45, 3)
        sources["gusset_enabled"] = "user"
        sources["gusset_thickness"] = "derived"
        sources["gusset_height"] = "derived"
        _add_default_assumption(assumptions, "Gusset thickness defaulted to bracket thickness.")
        _add_default_assumption(assumptions, "Gusset height defaulted to 45% of the shorter leg.")

    parameter_table = _build_l_parameter_table(values, sources, units, feature_flags, assumptions, unknowns, warnings)
    intent = _build_l_intent(prompt, feature_flags, assumptions, unknowns, warnings)
    constraints = _build_l_constraints(feature_flags)
    feature_plan = _build_l_feature_plan(feature_flags)
    return ParsedPrompt(intent=intent, parameter_table=parameter_table, constraint_graph=constraints, feature_plan=feature_plan, warnings=warnings)


def parse_prompt(prompt: str) -> ParsedPrompt:
    """Parse a supported prompt into structured IntentForge artifacts."""

    if _has_l_bracket_object(_normalise(prompt)):
        return parse_l_bracket_prompt(prompt)
    return parse_bracket_prompt(prompt)


def parse_requirements(prompt: str) -> IntentSpec:
    """Backward-compatible wrapper returning only the parsed intent."""

    return parse_prompt(prompt).intent
