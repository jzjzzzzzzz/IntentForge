"""Schema guardrails for optional LLM translations."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from intentforge.parser import ParsedPrompt, parse_prompt

SUPPORTED_FAMILIES = {"wall_mounted_bracket", "l_bracket"}
FEATURE_STATES = {"requested_by_user", "defaulted_by_system", "omitted"}
WALL_FEATURES = {"mounting_holes", "center_cutout", "rounded_corners", "edge_fillets"}
L_BRACKET_FEATURES = {
    "base_leg",
    "vertical_leg",
    "base_mounting_holes",
    "vertical_mounting_holes",
    "inside_fillet",
    "outside_edge_fillets",
    "triangular_gusset",
}
WALL_NUMERIC_PARAMETERS = {
    "width",
    "height",
    "thickness",
    "hole_count",
    "hole_diameter",
    "hole_spacing",
    "hole_spacing_x",
    "hole_spacing_y",
    "corner_radius",
    "cutout_width",
    "cutout_height",
    "edge_fillet_radius",
}
L_NUMERIC_PARAMETERS = {
    "base_leg_length",
    "vertical_leg_length",
    "bracket_width",
    "thickness",
    "base_hole_count",
    "vertical_hole_count",
    "hole_diameter",
    "base_hole_spacing",
    "vertical_hole_spacing",
    "inside_fillet_radius",
    "outside_edge_fillet_radius",
    "gusset_thickness",
    "gusset_height",
}


class LLMSchemaGuardError(ValueError):
    """Raised when LLM output violates IntentForge guardrails."""


@dataclass(frozen=True)
class GuardedIntentTranslation:
    """A schema-guarded intent translation ready for deterministic workflows."""

    llm_output: dict[str, Any]
    normalized_prompt: str
    parsed: ParsedPrompt
    warnings: list[str]


@dataclass(frozen=True)
class GuardedEditTranslation:
    """A schema-guarded edit translation ready for deterministic workflows."""

    llm_output: dict[str, Any]
    edit_request: dict[str, Any]
    normalized_edit_text: str
    warnings: list[str]


def _json_text(data: Any) -> str:
    return json.dumps(data, sort_keys=True).lower()


def _contains_unsupported_text(text: str) -> str | None:
    patterns = [
        (r"\bgear\b", "Unsupported object type: gear."),
        (r"\benclosure\b", "Unsupported object type: enclosure."),
        (r"\bdrone\s+frame\b", "Unsupported object type: drone frame."),
        (r"\bhinge\b", "Unsupported object type: hinge."),
        (r"\bshaft\s+coupler\b", "Unsupported object type: shaft coupler."),
        (r"\barbitrary\s+(?:freeform\s+)?cad\b", "Unsupported object type: arbitrary freeform CAD."),
        (r"\bcurved\s+l[-\s]?bracket\b", "Unsupported geometry: curved L-brackets are not supported."),
        (r"\bsheet[-\s]?metal\s+flat\s+pattern\b|\bflat\s+pattern\b", "Unsupported geometry: sheet-metal flat patterns are not supported."),
        (r"\barbitrary\s+(?:hole\s+)?coordinates\b|\bfreeform\s+holes?.*coordinates\b", "Unsupported geometry: arbitrary hole coordinates are not supported."),
        (r"\bmake it better\b|\bmake it stronger\b|\bmake it cheaper\b|\boptimi[sz]e\b", "Ambiguous request: provide a measurable parameter or supported feature."),
    ]
    for pattern, message in patterns:
        if re.search(pattern, text):
            return message
    return None


def _require_object(data: Any, label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise LLMSchemaGuardError(f"{label} must be a JSON object.")
    return data


def _parameters(data: dict[str, Any]) -> dict[str, Any]:
    parameters = data.get("parameters", {})
    if not isinstance(parameters, dict):
        raise LLMSchemaGuardError("parameters must be a JSON object.")
    return parameters


def _feature_flags(data: dict[str, Any]) -> dict[str, Any]:
    feature_flags = data.get("feature_flags", {})
    if not isinstance(feature_flags, dict):
        raise LLMSchemaGuardError("feature_flags must be a JSON object.")
    return feature_flags


def _is_active(flag: Any) -> bool:
    return isinstance(flag, dict) and flag.get("state") in {"requested_by_user", "defaulted_by_system"}


def _validate_feature_flags(feature_flags: dict[str, Any], object_type: str) -> None:
    allowed = WALL_FEATURES if object_type == "wall_mounted_bracket" else L_BRACKET_FEATURES
    for feature, flag in feature_flags.items():
        if feature not in allowed:
            raise LLMSchemaGuardError(f"Unsupported feature for {object_type}: {feature}.")
        if not isinstance(flag, dict):
            raise LLMSchemaGuardError(f"feature flag {feature} must be an object.")
        state = flag.get("state")
        if state not in FEATURE_STATES:
            raise LLMSchemaGuardError(f"feature flag {feature} has unsupported state: {state}.")
        if "hole_count" in flag:
            _validate_hole_count(object_type, feature, flag["hole_count"])


def _validate_hole_count(object_type: str, feature: str, value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise LLMSchemaGuardError(f"{feature} hole_count must be numeric.")
    count = int(value)
    if object_type == "wall_mounted_bracket" and count not in {0, 2, 4}:
        raise LLMSchemaGuardError("Unsupported mounting-hole count: wall_mounted_bracket supports 0, 2, or 4 holes.")
    if object_type == "l_bracket" and count not in {0, 2}:
        raise LLMSchemaGuardError("Unsupported L-bracket hole count: use 0 or 2 holes per leg.")


def _validate_numeric_parameters(parameters: dict[str, Any], object_type: str) -> None:
    allowed = WALL_NUMERIC_PARAMETERS if object_type == "wall_mounted_bracket" else L_NUMERIC_PARAMETERS
    for name, value in parameters.items():
        if name not in allowed:
            raise LLMSchemaGuardError(f"Unsupported parameter for {object_type}: {name}.")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise LLMSchemaGuardError(f"Parameter {name} must be numeric.")
        if name.endswith("count"):
            _validate_hole_count(
                object_type,
                "mounting_holes" if object_type == "wall_mounted_bracket" else name,
                value,
            )
        elif value <= 0 and name not in {"corner_radius", "edge_fillet_radius", "inside_fillet_radius", "outside_edge_fillet_radius"}:
            raise LLMSchemaGuardError(f"Parameter {name} must be greater than zero.")


def _num(parameters: dict[str, Any], name: str) -> float | int | None:
    value = parameters.get(name)
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _flag_state(feature_flags: dict[str, Any], name: str) -> str:
    flag = feature_flags.get(name)
    if isinstance(flag, dict):
        return str(flag.get("state", "omitted"))
    return "omitted"


def _wall_normalized_prompt(data: dict[str, Any]) -> str:
    parameters = _parameters(data)
    feature_flags = _feature_flags(data)
    units = str(data.get("units") or "mm")
    parts = ["Make a wall-mounted bracket"]
    if (value := _num(parameters, "width")) is not None:
        parts.append(f"{value} {units} wide")
    if (value := _num(parameters, "height")) is not None:
        parts.append(f"{value} {units} tall")
    if (value := _num(parameters, "thickness")) is not None:
        parts.append(f"{value} {units} thick")

    hole_flag = feature_flags.get("mounting_holes", {})
    hole_count = int(parameters.get("hole_count", hole_flag.get("hole_count", 0)) or 0) if isinstance(hole_flag, dict) else int(parameters.get("hole_count", 0) or 0)
    if _is_active(hole_flag) or hole_count:
        if hole_count == 4:
            parts.append("with four corner screw holes")
        else:
            parts.append("with two screw holes")
        if (value := _num(parameters, "hole_diameter")) is not None:
            parts.append(f"and {value} {units} holes")
        if (x := _num(parameters, "hole_spacing_x")) is not None and (y := _num(parameters, "hole_spacing_y")) is not None:
            parts.append(f"and hole spacing {x} {units} by {y} {units}")
        elif (value := _num(parameters, "hole_spacing")) is not None:
            parts.append(f"and hole spacing {value} {units}")
    elif _flag_state(feature_flags, "mounting_holes") == "omitted":
        parts.append("with no holes")

    if _is_active(feature_flags.get("center_cutout")):
        parts.append("and a center cutout")
        if (value := _num(parameters, "cutout_width")) is not None:
            parts.append(f"with cutout width {value} {units}")
        if (value := _num(parameters, "cutout_height")) is not None:
            parts.append(f"and cutout height {value} {units}")
    if _is_active(feature_flags.get("rounded_corners")):
        parts.append("and rounded corners")
    if _is_active(feature_flags.get("edge_fillets")):
        parts.append("and edge fillets")
    return ", ".join(parts) + "."


def _l_normalized_prompt(data: dict[str, Any]) -> str:
    parameters = _parameters(data)
    feature_flags = _feature_flags(data)
    units = str(data.get("units") or "mm")
    parts = ["Make an L-bracket"]
    if (value := _num(parameters, "base_leg_length")) is not None:
        parts.append(f"{value} {units} base leg")
    if (value := _num(parameters, "vertical_leg_length")) is not None:
        parts.append(f"{value} {units} vertical leg")
    if (value := _num(parameters, "bracket_width")) is not None:
        parts.append(f"{value} {units} wide")
    if (value := _num(parameters, "thickness")) is not None:
        parts.append(f"{value} {units} thick")

    base_active = _is_active(feature_flags.get("base_mounting_holes")) or int(parameters.get("base_hole_count", 0) or 0) == 2
    vertical_active = _is_active(feature_flags.get("vertical_mounting_holes")) or int(parameters.get("vertical_hole_count", 0) or 0) == 2
    if base_active and vertical_active:
        parts.append("with two holes on the base and two holes on the vertical face")
    elif base_active:
        parts.append("with two holes on the base")
    elif vertical_active:
        parts.append("with two holes on the vertical face")
    else:
        parts.append("with no holes")
    if (value := _num(parameters, "hole_diameter")) is not None and (base_active or vertical_active):
        parts.append(f"and {value} {units} holes")
    if _is_active(feature_flags.get("triangular_gusset")):
        parts.append("with a triangular gusset")
    if _is_active(feature_flags.get("inside_fillet")):
        parts.append("with an inside fillet")
    if _is_active(feature_flags.get("outside_edge_fillets")):
        parts.append("with outside edge fillets")
    return ", ".join(parts) + "."


def validate_intent_translation(data: Any, original_prompt: str) -> GuardedIntentTranslation:
    """Validate LLM prompt translation and normalize it for deterministic parsing."""

    raw = _require_object(data, "intent translation")
    scan_text = f"{original_prompt.lower()} {_json_text(raw)}"
    if message := _contains_unsupported_text(scan_text):
        raise LLMSchemaGuardError(message)
    object_type = str(raw.get("object_type") or raw.get("family") or "")
    if object_type not in SUPPORTED_FAMILIES:
        raise LLMSchemaGuardError(f"Unsupported object type: {object_type or 'missing'}.")
    parameters = _parameters(raw)
    feature_flags = _feature_flags(raw)
    _validate_numeric_parameters(parameters, object_type)
    _validate_feature_flags(feature_flags, object_type)
    normalized_prompt = _wall_normalized_prompt(raw) if object_type == "wall_mounted_bracket" else _l_normalized_prompt(raw)
    parsed = parse_prompt(normalized_prompt)
    warnings = list(raw.get("warnings", [])) if isinstance(raw.get("warnings", []), list) else []
    return GuardedIntentTranslation(
        llm_output=raw,
        normalized_prompt=normalized_prompt,
        parsed=parsed,
        warnings=warnings,
    )


def _normalize_edit_text(edit_request: dict[str, Any], object_type: str) -> str:
    edits = edit_request.get("edits", [])
    fragments: list[str] = []
    for edit in edits:
        edit_type = edit.get("type")
        if edit_type == "set_parameter":
            parameter = str(edit.get("parameter"))
            value = edit.get("value")
            if parameter in {"width", "back_plate_width_mm"}:
                fragments.append(f"Set width to {value} mm.")
            elif parameter in {"height", "back_plate_height_mm"}:
                fragments.append(f"Set height to {value} mm.")
            elif parameter in {"thickness", "back_plate_thickness_mm", "l_thickness", "thickness_mm"}:
                fragments.append(f"Set thickness to {value} mm.")
            elif parameter in {"base_leg_length", "base_leg_length_mm"}:
                fragments.append(f"Make the base leg {value} mm long.")
            elif parameter in {"vertical_leg_length", "vertical_leg_length_mm"}:
                fragments.append(f"Make the vertical leg {value} mm tall.")
            elif parameter in {"bracket_width", "bracket_width_mm"}:
                fragments.append(f"Set bracket width to {value} mm.")
            elif parameter in {"hole_count", "mounting_hole_count"}:
                fragments.append(f"Change it to {int(value)} mounting holes.")
            elif parameter in {"base_hole_count"}:
                fragments.append(f"Add {int(value)} holes to the base leg.")
            elif parameter in {"vertical_hole_count"}:
                fragments.append(f"Add {int(value)} holes to the vertical leg.")
        elif edit_type == "enable_feature":
            feature = str(edit.get("feature"))
            if feature == "triangular_gusset":
                fragments.append("Add a triangular gusset.")
            elif feature == "base_mounting_holes":
                fragments.append("Add two holes to the base leg.")
            elif feature == "vertical_mounting_holes":
                fragments.append("Add two holes to the vertical leg.")
            elif feature == "center_cutout":
                fragments.append("Add a center cutout.")
            elif feature == "mounting_holes":
                fragments.append("Add two screw holes.")
            elif feature == "rounded_corners":
                fragments.append("Add rounded corners.")
        elif edit_type == "disable_feature":
            feature = str(edit.get("feature"))
            if feature == "triangular_gusset":
                fragments.append("Remove the gusset.")
            elif feature == "base_mounting_holes":
                fragments.append("Remove the base holes.")
            elif feature == "vertical_mounting_holes":
                fragments.append("Remove the vertical holes.")
            elif feature == "center_cutout":
                fragments.append("Remove the center cutout.")
            elif feature == "mounting_holes":
                fragments.append("Remove the mounting holes.")
            elif feature == "rounded_corners":
                fragments.append("Remove rounded corners.")
    if not fragments:
        raise LLMSchemaGuardError("Ambiguous edit: no supported measurable edit was translated.")
    return " ".join(fragments)


def validate_edit_translation(data: Any, edit_text: str, object_type: str) -> GuardedEditTranslation:
    """Validate LLM edit translation and normalize it for deterministic edit handling."""

    if object_type not in SUPPORTED_FAMILIES:
        raise LLMSchemaGuardError(f"Unsupported object type: {object_type}.")
    raw = _require_object(data, "edit translation")
    scan_text = f"{edit_text.lower()} {_json_text(raw)}"
    if message := _contains_unsupported_text(scan_text):
        raise LLMSchemaGuardError(message)
    edits = raw.get("edits")
    if not isinstance(edits, list) or not edits:
        raise LLMSchemaGuardError("Ambiguous edit: no supported measurable edit was translated.")
    allowed_features = WALL_FEATURES if object_type == "wall_mounted_bracket" else L_BRACKET_FEATURES
    allowed_parameters = WALL_NUMERIC_PARAMETERS if object_type == "wall_mounted_bracket" else L_NUMERIC_PARAMETERS | {"width", "l_thickness"}
    for edit in edits:
        if not isinstance(edit, dict):
            raise LLMSchemaGuardError("Each edit must be a JSON object.")
        edit_type = edit.get("type")
        if edit_type not in {"set_parameter", "enable_feature", "disable_feature"}:
            raise LLMSchemaGuardError(f"Unsupported edit type: {edit_type}.")
        if edit_type == "set_parameter":
            parameter = str(edit.get("parameter") or "")
            if parameter not in allowed_parameters and parameter not in {"hole_count", "mounting_hole_count"}:
                raise LLMSchemaGuardError(f"Unsupported edit parameter for {object_type}: {parameter}.")
            value = edit.get("value")
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise LLMSchemaGuardError(f"Edit parameter {parameter} must have a numeric value.")
            if "count" in parameter:
                _validate_hole_count(object_type, parameter, value)
            elif value <= 0:
                raise LLMSchemaGuardError(f"Edit parameter {parameter} must be greater than zero.")
        else:
            feature = str(edit.get("feature") or "")
            if feature not in allowed_features:
                raise LLMSchemaGuardError(f"Unsupported edit feature for {object_type}: {feature}.")
    preserve = raw.get("preserve", [])
    if not isinstance(preserve, list):
        raise LLMSchemaGuardError("preserve must be a list.")
    normalized_edit_text = _normalize_edit_text(raw, object_type)
    guarded = {
        "edits": edits,
        "preserve": [str(item) for item in preserve],
        "assumptions": raw.get("assumptions", []) if isinstance(raw.get("assumptions", []), list) else [],
        "warnings": raw.get("warnings", []) if isinstance(raw.get("warnings", []), list) else [],
    }
    return GuardedEditTranslation(
        llm_output=raw,
        edit_request=guarded,
        normalized_edit_text=normalized_edit_text,
        warnings=list(guarded["warnings"]),
    )
