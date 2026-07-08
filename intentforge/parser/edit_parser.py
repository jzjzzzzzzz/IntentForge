"""Deterministic natural-language edit parser for Phase 6."""

from __future__ import annotations

import re
from typing import Any

from intentforge.features import feature_flags_for_parameter_table


class UnsupportedEditError(ValueError):
    """Raised when an edit request is unsupported or not measurable."""


UNSUPPORTED_OBJECTS = [
    "gear",
    "enclosure",
    "shaft coupler",
    "coupler",
    "hinge",
    "drone frame",
    "adjustable bracket",
]

VAGUE_EDIT_PATTERNS = [
    r"\bmake it better\b",
    r"\bmake it stronger\b",
    r"\bmake it more beautiful\b",
    r"\boptimi[sz]e it\b",
    r"\bmake it cheaper\b",
    r"\bcurved\s+l[-\s]?bracket\b",
    r"\b(?:sheet\s+metal|sheetmetal)\s+flat\s+pattern\b",
    r"\bflat\s+pattern\b",
    r"\bcircular\s+(?:hole\s+)?pattern\b",
    r"\bdiagonal\s+(?:hole\s+)?pattern\b",
    r"\bcircular\s+(?:screw\s+|mounting\s+|corner\s+)?holes?\b",
    r"\bdiagonal\s+(?:screw\s+|mounting\s+|corner\s+)?holes?\b",
    r"\barbitrary\s+(?:hole\s+)?(?:coordinates|placement|pattern)\b",
]

NUMBER_UNIT = r"(?P<value>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)"


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _reject_unsupported(text: str) -> None:
    for object_name in UNSUPPORTED_OBJECTS:
        if re.search(rf"\b{re.escape(object_name)}s?\b", text):
            raise UnsupportedEditError(
                "Unsupported object edit. Currently only supported bracket-family edits are available."
            )
    for pattern in VAGUE_EDIT_PATTERNS:
        if re.search(pattern, text):
            raise UnsupportedEditError(
                "Unsupported edit for Phase 6. Please provide a measurable parameter or supported feature change."
            )


def _number(pattern: str, text: str, value_group: str = "value") -> float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return float(match.group(value_group))


def _append_set(edits: list[dict[str, Any]], parameter: str, value: float) -> None:
    if any(edit.get("type") == "set_parameter" and edit.get("parameter") == parameter for edit in edits):
        return
    edits.append({"type": "set_parameter", "parameter": parameter, "value": value})


def _append_feature(edits: list[dict[str, Any]], edit_type: str, feature: str, reason: str) -> None:
    if any(edit.get("type") == edit_type and edit.get("feature") == feature for edit in edits):
        return
    edits.append({"type": edit_type, "feature": feature, "reason": reason})


def _is_l_bracket_context(existing_params: Any) -> bool:
    return getattr(existing_params, "family", None) == "l_bracket"


def _parse_l_parameter_edits(text: str, edits: list[dict[str, Any]], assumptions: list[str]) -> None:
    base_leg = (
        _number(rf"\b(?:make|set|change)\s+(?:the\s+)?base\s+leg\s*(?:length\s*)?(?:to)?\s*{NUMBER_UNIT}\b", text)
        or _number(rf"\b(?:make|set|change)\s+(?:the\s+)?base\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
        or _number(rf"\b{NUMBER_UNIT}\s+(?:base\s+leg|base)\b", text)
    )
    if base_leg is not None:
        _append_set(edits, "base_leg_length", base_leg)

    vertical_leg = (
        _number(rf"\b(?:make|set|change)\s+(?:the\s+)?(?:vertical\s+leg|upright)\s*(?:length|height|tall)?\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
        or _number(rf"\b{NUMBER_UNIT}\s+(?:vertical\s+leg|upright)\b", text)
    )
    if vertical_leg is not None:
        _append_set(edits, "vertical_leg_length", vertical_leg)

    bracket_width = (
        _number(rf"\b(?:set|change)\s+(?:the\s+)?(?:bracket\s+)?width\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
        or _number(rf"\b{NUMBER_UNIT}\s+(?:bracket\s+)?wide\b", text)
    )
    if bracket_width is not None:
        _append_set(edits, "bracket_width", bracket_width)

    thickness = (
        _number(rf"\b(?:make it|set|change)\s+(?:the\s+)?thickness\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
        or _number(rf"\b(?:make it|change it to)?\s*{NUMBER_UNIT}\s+thick\b", text)
    )
    if thickness is not None:
        _append_set(edits, "l_thickness", thickness)

    hole_diameter = _number(rf"\b(?:change|set|make)\s+(?:the\s+)?hole\s+diameter\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
    if hole_diameter is not None:
        _append_set(edits, "hole_diameter_mm", hole_diameter)

    base_spacing = _number(rf"\bbase\s+hole\s+spacing\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
    if base_spacing is not None:
        _append_set(edits, "base_hole_spacing", base_spacing)

    vertical_spacing = _number(rf"\bvertical\s+hole\s+spacing\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
    if vertical_spacing is not None:
        _append_set(edits, "vertical_hole_spacing", vertical_spacing)

    if re.search(r"\badd\s+(?:a\s+)?triangular\s+gusset\b|\badd\s+(?:a\s+)?gusset\b", text):
        assumptions.append("Gusset thickness and height will use safe defaults if not already present.")


def _parse_parameter_edits(text: str, edits: list[dict[str, Any]], assumptions: list[str], existing_params: Any) -> None:
    if _is_l_bracket_context(existing_params):
        _parse_l_parameter_edits(text, edits, assumptions)
        return

    cutout_width_phrase = bool(re.search(rf"\bcutout\s+{NUMBER_UNIT}\s+(?:wide|width)\b", text))
    cutout_height_phrase = bool(re.search(rf"\bcutout\b.*\b{NUMBER_UNIT}\s+(?:tall|high|height)\b", text))
    width = _number(rf"\b(?:make it|set|change)\s+(?:the\s+)?width\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
    if width is None and not cutout_width_phrase:
        width = _number(rf"\b(?:make it|change it to)?\s*{NUMBER_UNIT}\s+wide\b", text)
    if width is not None:
        _append_set(edits, "width", width)

    height = _number(rf"\b(?:set|change)\s+(?:the\s+)?height\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
    if height is None and not cutout_height_phrase:
        height = _number(rf"\b(?:make it|change it to)?\s*{NUMBER_UNIT}\s+(?:tall|high)\b", text)
    if height is not None:
        _append_set(edits, "height", height)
    elif re.search(r"\bmake it taller\b", text):
        if existing_params is None:
            raise UnsupportedEditError("Ambiguous height edit: specify a target height in millimeters.")
        try:
            old_height = existing_params.get("back_plate_height_mm").value
        except KeyError as exc:
            raise UnsupportedEditError("Ambiguous height edit: existing height is unavailable.") from exc
        if isinstance(old_height, bool) or not isinstance(old_height, int | float):
            raise UnsupportedEditError("Ambiguous height edit: existing height is not numeric.")
        new_height = float(old_height) + 10.0
        assumptions.append("Height increased by 10 mm because no target height was specified.")
        _append_set(edits, "height", new_height)

    thickness = (
        _number(rf"\b(?:make it|set|change)\s+(?:the\s+)?thickness\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
        or _number(rf"\b(?:make it|change it to)?\s*{NUMBER_UNIT}\s+thick\b", text)
    )
    if thickness is not None:
        _append_set(edits, "thickness", thickness)

    hole_diameter = _number(
        rf"\b(?:change|set|make)\s+(?:the\s+)?hole\s+diameter\s*(?:to)?\s*{NUMBER_UNIT}\b",
        text,
    )
    if hole_diameter is not None:
        _append_set(edits, "hole_diameter", hole_diameter)

    hole_spacing = _number(
        rf"\b(?:increase\s+|change\s+|set\s+)?(?:the\s+)?hole\s+spacing\s*(?:to)?\s*{NUMBER_UNIT}\b",
        text,
    )
    if hole_spacing is not None:
        _append_set(edits, "hole_spacing", hole_spacing)
    spacing_xy = _parse_hole_spacing_xy(text)
    if spacing_xy is not None:
        spacing_x, spacing_y = spacing_xy
        _append_set(edits, "hole_spacing_x", spacing_x)
        _append_set(edits, "hole_spacing_y", spacing_y)

    cutout_size = re.search(
        rf"\b(?:add\s+a\s+)?(?P<width>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\s+by\s+"
        rf"(?P<height>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\s+(?:center\s+)?cutout\b",
        text,
    )
    if cutout_size:
        _append_feature(edits, "enable_feature", "center_cutout", "Edit request mentioned a center cutout.")
        _append_set(edits, "cutout_width", float(cutout_size.group("width")))
        _append_set(edits, "cutout_height", float(cutout_size.group("height")))
    elif "cutout" in text:
        cutout_width = _number(
            rf"\b(?:make|set|change)\s+(?:the\s+)?cutout\s+{NUMBER_UNIT}\s+(?:wide|width)\b",
            text,
        ) or _number(rf"\bcutout\s+width\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
        cutout_height = _number(
            rf"\b(?:and\s+)?(?P<value>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\s+(?:tall|high)\b",
            text,
        ) or _number(rf"\bcutout\s+height\s*(?:to)?\s*{NUMBER_UNIT}\b", text)
        if cutout_width is not None:
            _append_set(edits, "cutout_width", cutout_width)
        if cutout_height is not None:
            _append_set(edits, "cutout_height", cutout_height)

    hole_count = _parse_hole_count(text)
    if hole_count is not None:
        if hole_count not in {2, 4}:
            raise UnsupportedEditError("Unsupported mounting-hole count for Phase 6.5. Use two or four holes.")
        _append_feature(edits, "enable_feature", "mounting_holes", "Edit request mentioned mounting holes.")
        _append_set(edits, "hole_count", float(hole_count))


def _parse_hole_spacing_xy(text: str) -> tuple[float, float] | None:
    match = re.search(
        r"\b(?:four\s+holes\s+spaced|hole\s+spacing)\s+(?P<x>\d+(?:\.\d+)?)\s*(?:mm|millimeters?|millimetres?)\s+by\s+"
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


def _parse_hole_count(text: str) -> int | None:
    if re.search(r"\bfour[-\s]hole\s+pattern\b", text):
        return 4
    if re.search(r"\btwo[-\s]hole\s+pattern\b", text):
        return 2
    word_numbers = {"one": 1, "two": 2, "three": 3, "four": 4}
    for word, count in word_numbers.items():
        if re.search(rf"\b(?:(?:add|to|use)\s+|change\s+it\s+to\s+)?{word}\s+(?:corner\s+)?(?:screw|mounting|corner)?\s*holes?\b", text):
            return count
    match = re.search(r"\b(?:(?:add|to|use)\s+|change\s+it\s+to\s+)?(?P<count>\d+)\s+(?:corner\s+)?(?:screw|mounting|corner)?\s*holes?\b", text)
    if match:
        return int(match.group("count"))
    return None


def _parse_preserve(text: str) -> list[str]:
    preserve: list[str] = []

    def add(item: str) -> None:
        if item not in preserve:
            preserve.append(item)

    if re.search(r"\bkeep\s+(?:the\s+)?same\s+thickness\b", text) or re.search(r"\bkeep\s+.*thickness\b", text):
        add("thickness")
    if re.search(r"\bkeep\s+.*hole\s+diameter\s+(?:unchanged|same)\b", text):
        add("hole_diameter")
    if re.search(r"\bpreserv(?:e|ing)\s+symmetry\b", text) or re.search(r"\bkeep\s+.*symmetr", text):
        add("mounting_hole_symmetry")
    if re.search(r"\bkeep\s+(?:the\s+)?holes?\s+(?:the\s+)?same\b", text):
        add("hole_diameter")
        add("hole_spacing")
        add("mounting_hole_symmetry")
    return preserve


def _parse_feature_edits(text: str, edits: list[dict[str, Any]], existing_params: Any = None) -> None:
    if _is_l_bracket_context(existing_params):
        if re.search(r"\badd\s+(?:two\s+|2\s+)?holes?\s+to\s+(?:the\s+)?base\s+leg\b", text):
            _append_feature(edits, "enable_feature", "base_mounting_holes", "Edit request added base-leg holes.")
            _append_set(edits, "base_hole_count", 2.0)
        if re.search(r"\bremove\s+(?:the\s+)?base\s+(?:mounting\s+|screw\s+)?holes?\b", text):
            _append_feature(edits, "disable_feature", "base_mounting_holes", "Edit request removed base-leg holes.")

        if re.search(r"\badd\s+(?:two\s+|2\s+)?holes?\s+to\s+(?:the\s+)?(?:vertical|upright)(?:\s+face|\s+leg)?\b", text):
            _append_feature(edits, "enable_feature", "vertical_mounting_holes", "Edit request added vertical-leg holes.")
            _append_set(edits, "vertical_hole_count", 2.0)
        if re.search(r"\bremove\s+(?:the\s+)?(?:vertical|upright)\s+(?:mounting\s+|screw\s+)?holes?\b", text):
            _append_feature(edits, "disable_feature", "vertical_mounting_holes", "Edit request removed vertical-leg holes.")

        if re.search(r"\badd\s+(?:a\s+)?(?:triangular\s+)?gusset\b", text):
            _append_feature(edits, "enable_feature", "triangular_gusset", "Edit request added a triangular gusset.")
        elif re.search(r"\bremove\s+(?:the\s+)?(?:triangular\s+)?gusset\b", text):
            _append_feature(edits, "disable_feature", "triangular_gusset", "Edit request removed the gusset.")

        if re.search(
            r"\b(?:three|3|four|4)\s+(?:base\s+|vertical\s+|upright\s+|mounting\s+|screw\s+)?holes?\b",
            text,
        ) or re.search(
            r"\b(?:three|3|four|4)\s+holes?\s+on\s+(?:the\s+)?(?:base|vertical|upright)(?:\s+face|\s+leg)?\b",
            text,
        ):
            raise UnsupportedEditError("Unsupported L-bracket hole count for Phase 10. Use 0 or 2 holes per leg.")
        return

    if re.search(r"\bremove\s+(?:the\s+)?(?:center\s+|central\s+)?cutout\b", text):
        _append_feature(edits, "disable_feature", "center_cutout", "Edit request removed the center cutout.")
    elif re.search(r"\badd\s+(?:a\s+)?(?:center\s+|central\s+)?cutout\b", text):
        _append_feature(edits, "enable_feature", "center_cutout", "Edit request added a center cutout.")

    if re.search(r"\bremove\s+(?:the\s+)?(?:mounting\s+|screw\s+)?holes?\b", text):
        _append_feature(edits, "disable_feature", "mounting_holes", "Edit request removed mounting holes.")
    elif re.search(r"\badd\s+(?:two\s+|2\s+|four\s+|4\s+)?(?:corner\s+|screw\s+|mounting\s+)?holes?\b", text):
        _append_feature(edits, "enable_feature", "mounting_holes", "Edit request added mounting holes.")

    if re.search(r"\badd\s+rounded\s+corners?\b", text):
        _append_feature(edits, "enable_feature", "rounded_corners", "Edit request added rounded corners.")
    elif re.search(r"\bremove\s+rounded\s+corners?\b", text):
        _append_feature(edits, "disable_feature", "rounded_corners", "Edit request removed rounded corners.")


def parse_edit_request(
    text: str,
    existing_params: Any = None,
    existing_feature_flags: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parse a simple natural-language edit into structured edit JSON."""

    if not text or not text.strip():
        raise UnsupportedEditError("Edit request must not be empty.")

    normalized = _normalise(text)
    _reject_unsupported(normalized)

    edits: list[dict[str, Any]] = []
    assumptions: list[str] = []
    warnings: list[str] = []
    preserve = _parse_preserve(normalized)

    _parse_feature_edits(normalized, edits, existing_params)
    _parse_parameter_edits(normalized, edits, assumptions, existing_params)

    if existing_feature_flags is None and existing_params is not None:
        existing_feature_flags = feature_flags_for_parameter_table(existing_params)

    if not edits:
        raise UnsupportedEditError(
            "Unsupported or ambiguous edit for Phase 6. Provide a measurable parameter or supported feature change."
        )

    return {
        "edits": edits,
        "preserve": preserve,
        "warnings": warnings,
        "assumptions": assumptions,
    }
