from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from intentforge.assurance import build_assurance_case, build_assurance_from_prompt
from intentforge.review import collect_review_evaluation_resources
from intentforge.workflows import edit_parse_apply_workflow, parse_build_workflow


ROOT = Path("/tmp/intentforge-phase24-test-fixtures")


@lru_cache(maxsize=1)
def review_resources():
    return collect_review_evaluation_resources()


@lru_cache(maxsize=None)
def static_case():
    return build_assurance_from_prompt(profile="static", family="wall_mounted_bracket")


@lru_cache(maxsize=None)
def standard_case(family: str = "wall_mounted_bracket", partial: bool = False):
    if family == "l_bracket":
        prompt = (
            "Make an L-bracket 80 mm wide with 60 mm legs, 8 mm thick, two holes on each leg, and an inside fillet."
            if partial else
            "Make an L-bracket 80 mm wide with 60 mm legs, 8 mm thick, and two holes on each leg."
        )
    elif partial:
        prompt = "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with rounded corners and two holes."
    else:
        prompt = "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes."
    return build_assurance_from_prompt(
        prompt, profile="standard", family=family, dry_run=True,
        output_root=ROOT / "output" / ("partial" if partial else family),
    )


@lru_cache(maxsize=None)
def full_case():
    return build_assurance_from_prompt(
        profile="full", family="wall_mounted_bracket",
        output_root=ROOT / "output" / "full",
    )


@lru_cache(maxsize=None)
def rejection_case():
    result = parse_build_workflow(
        "Make a gear with 24 teeth.", ROOT / "output" / "rejection", dry_run=True,
    )
    result["object_type"] = "wall_mounted_bracket"
    return build_assurance_case(result, profile="static", input_request="Make a gear with 24 teeth.")


@lru_cache(maxsize=None)
def edit_case():
    result = edit_parse_apply_workflow(
        "bracket", "Make it 150 mm wide but keep the same thickness.",
        ROOT / "output" / "edit", dry_run=True,
    )
    return build_assurance_case(result, profile="standard", input_request="width edit")
