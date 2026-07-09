"""Deterministic mock LLM provider for tests and local demos."""

from __future__ import annotations

import re
from typing import Any

from intentforge.llm.provider import LLMProvider


def _last_user_message(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _number(text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group("value"))
    return None


def _feature(state: str, reason: str, **metadata: Any) -> dict[str, Any]:
    return {"state": state, "reason": reason, **metadata}


class MockLLMProvider(LLMProvider):
    """Rule-backed fake provider that returns LLM-shaped JSON without network calls."""

    def complete_json(self, messages: list[dict[str, str]], schema_name: str) -> dict[str, Any]:
        user_text = _last_user_message(messages)
        if schema_name == "intent_translation":
            return self._intent_translation(user_text)
        if schema_name == "edit_translation":
            return self._edit_translation(user_text)
        raise ValueError(f"unsupported mock schema: {schema_name}")

    def _intent_translation(self, prompt: str) -> dict[str, Any]:
        text = prompt.lower()
        unsupported = {
            "gear": "gear",
            "enclosure": "enclosure",
            "drone frame": "drone_frame",
            "hinge": "hinge",
            "shaft coupler": "shaft_coupler",
        }
        for phrase, object_type in unsupported.items():
            if phrase in text:
                return {
                    "object_type": object_type,
                    "units": "mm",
                    "parameters": {},
                    "feature_flags": {},
                    "assumptions": [],
                    "unknowns": [],
                    "warnings": [f"Prompt requested unsupported object: {phrase}."],
                }

        if "curved l-bracket" in text or "curved l bracket" in text:
            return {
                "object_type": "l_bracket",
                "units": "mm",
                "parameters": {},
                "feature_flags": {"curved": _feature("requested_by_user", "Prompt requested curved L-bracket geometry.")},
                "assumptions": [],
                "unknowns": [],
                "warnings": ["Curved L-bracket geometry requested."],
            }

        if re.search(r"\bl[-\s]?bracket\b|right angle bracket|90 degree bracket", text):
            return self._l_bracket_intent(text)
        return self._wall_bracket_intent(text)

    def _wall_bracket_intent(self, text: str) -> dict[str, Any]:
        width = _number(text, [r"(?P<value>\d+(?:\.\d+)?)\s*mm\s+wide", r"width\s+(?P<value>\d+(?:\.\d+)?)\s*mm"])
        height = _number(text, [r"(?P<value>\d+(?:\.\d+)?)\s*mm\s+(?:tall|high)", r"height\s+(?P<value>\d+(?:\.\d+)?)\s*mm"])
        thickness = _number(text, [r"(?P<value>\d+(?:\.\d+)?)\s*mm\s+thick", r"thickness\s+(?P<value>\d+(?:\.\d+)?)\s*mm"])
        hole_diameter = _number(text, [r"(?P<value>\d+(?:\.\d+)?)\s*mm\s+(?:screw\s+)?holes?", r"hole diameter\s+(?P<value>\d+(?:\.\d+)?)\s*mm"])
        parameters: dict[str, Any] = {}
        if width is not None:
            parameters["width"] = width
        if height is not None:
            parameters["height"] = height
        if thickness is not None:
            parameters["thickness"] = thickness
        if hole_diameter is not None:
            parameters["hole_diameter"] = hole_diameter

        hole_count = 0
        if re.search(r"\b(?:two|2)\s+(?:screw\s+|mounting\s+)?holes?\b", text):
            hole_count = 2
        if re.search(r"\b(?:four|4)\s+(?:corner\s+|screw\s+|mounting\s+)?holes?\b", text):
            hole_count = 4
        if re.search(r"\b(?:three|3|five|5)\s+(?:screw\s+|mounting\s+)?holes?\b", text):
            hole_count = 3
        if hole_count:
            parameters["hole_count"] = hole_count
        feature_flags = {
            "mounting_holes": _feature(
                "requested_by_user" if hole_count else "omitted",
                "Prompt mentioned mounting holes." if hole_count else "Prompt did not mention mounting holes.",
                hole_count=hole_count,
            ),
            "center_cutout": _feature(
                "requested_by_user" if "cutout" in text or "opening" in text else "omitted",
                "Prompt mentioned a center cutout." if "cutout" in text or "opening" in text else "Prompt did not mention a center cutout.",
            ),
            "rounded_corners": _feature(
                "requested_by_user" if "rounded corner" in text or "rounded corners" in text else "omitted",
                "Prompt mentioned rounded corners." if "rounded corner" in text or "rounded corners" in text else "Prompt did not mention rounded corners.",
            ),
            "edge_fillets": _feature("omitted", "Prompt did not mention edge fillets."),
        }
        return {
            "object_type": "wall_mounted_bracket",
            "units": "mm",
            "parameters": parameters,
            "feature_flags": feature_flags,
            "assumptions": [],
            "unknowns": ["material", "load requirement"],
            "warnings": [],
        }

    def _l_bracket_intent(self, text: str) -> dict[str, Any]:
        parameters: dict[str, Any] = {}
        base = _number(text, [r"(?P<value>\d+(?:\.\d+)?)\s*mm\s+base", r"base\s+leg\s+(?P<value>\d+(?:\.\d+)?)\s*mm"])
        vertical = _number(text, [r"(?P<value>\d+(?:\.\d+)?)\s*mm\s+(?:vertical|upright)", r"vertical\s+leg\s+(?P<value>\d+(?:\.\d+)?)\s*mm"])
        width = _number(text, [r"(?P<value>\d+(?:\.\d+)?)\s*mm\s+wide", r"width\s+(?P<value>\d+(?:\.\d+)?)\s*mm"])
        thickness = _number(text, [r"(?P<value>\d+(?:\.\d+)?)\s*mm\s+thick", r"thickness\s+(?P<value>\d+(?:\.\d+)?)\s*mm"])
        if base is not None:
            parameters["base_leg_length"] = base
        if vertical is not None:
            parameters["vertical_leg_length"] = vertical
        if width is not None:
            parameters["bracket_width"] = width
        if thickness is not None:
            parameters["thickness"] = thickness

        base_holes = bool(re.search(r"(?:two|2)\s+holes?\s+on\s+(?:the\s+)?base|base\s+holes?", text))
        vertical_holes = bool(re.search(r"(?:two|2)\s+holes?\s+on\s+(?:the\s+)?vertical|vertical\s+holes?|vertical face", text))
        no_holes = "no holes" in text or "without holes" in text
        if base_holes:
            parameters["base_hole_count"] = 2
        if vertical_holes:
            parameters["vertical_hole_count"] = 2

        feature_flags = {
            "base_leg": _feature("defaulted_by_system", "Required L-bracket base leg."),
            "vertical_leg": _feature("defaulted_by_system", "Required L-bracket vertical leg."),
            "base_mounting_holes": _feature(
                "requested_by_user" if base_holes and not no_holes else "omitted",
                "Prompt requested base holes." if base_holes else "Prompt did not mention base holes.",
                hole_count=2 if base_holes and not no_holes else 0,
            ),
            "vertical_mounting_holes": _feature(
                "requested_by_user" if vertical_holes and not no_holes else "omitted",
                "Prompt requested vertical holes." if vertical_holes else "Prompt did not mention vertical holes.",
                hole_count=2 if vertical_holes and not no_holes else 0,
            ),
            "inside_fillet": _feature("omitted", "Prompt did not mention inside fillet."),
            "outside_edge_fillets": _feature("omitted", "Prompt did not mention outside edge fillets."),
            "triangular_gusset": _feature(
                "requested_by_user" if "gusset" in text else "omitted",
                "Prompt requested a triangular gusset." if "gusset" in text else "Prompt did not mention a gusset.",
            ),
        }
        return {
            "object_type": "l_bracket",
            "units": "mm",
            "parameters": parameters,
            "feature_flags": feature_flags,
            "assumptions": [],
            "unknowns": ["material", "load requirement"],
            "warnings": [],
        }

    def _edit_translation(self, user_text: str) -> dict[str, Any]:
        text = user_text.lower()
        edit_text = text.split("edit=", 1)[-1]
        if any(phrase in edit_text for phrase in ["make it better", "stronger", "cheaper", "optimize"]):
            return {"edits": [], "preserve": [], "assumptions": [], "warnings": ["Vague edit requested."]}
        if re.search(r"\b(?:three|3|five|5)\s+(?:base\s+|vertical\s+|mounting\s+)?holes?\b", edit_text):
            return {
                "edits": [{"type": "set_parameter", "parameter": "hole_count", "value": 3}],
                "preserve": [],
                "assumptions": [],
                "warnings": ["Unsupported hole count requested."],
            }
        if "arbitrary" in edit_text and "coordinates" in edit_text:
            return {"edits": [{"type": "enable_feature", "feature": "arbitrary_holes"}], "preserve": [], "assumptions": [], "warnings": []}
        if "gusset" in edit_text and "remove" not in edit_text:
            return {
                "edits": [{"type": "enable_feature", "feature": "triangular_gusset", "reason": "Edit requested a gusset."}],
                "preserve": [],
                "assumptions": [],
                "warnings": [],
            }
        width = _number(edit_text, [r"(?P<value>\d+(?:\.\d+)?)\s*mm\s+wide", r"width\s+(?:to\s+)?(?P<value>\d+(?:\.\d+)?)\s*mm"])
        if width is not None:
            preserve = ["thickness"] if "keep" in edit_text and "thickness" in edit_text else []
            return {
                "edits": [{"type": "set_parameter", "parameter": "width", "value": width}],
                "preserve": preserve,
                "assumptions": [],
                "warnings": [],
            }
        return {"edits": [], "preserve": [], "assumptions": [], "warnings": ["No supported edit was found."]}
