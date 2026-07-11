"""Review-decision serialization and loading helpers."""

from __future__ import annotations

from pathlib import Path

from intentforge.review.schema import ReviewDecision


def serialize_review_decision(decision: ReviewDecision | dict) -> str:
    record = decision if isinstance(decision, ReviewDecision) else ReviewDecision.model_validate(decision)
    return record.to_json()


def load_review_decision(path: str | Path) -> ReviewDecision:
    return ReviewDecision.model_validate_json(Path(path).read_text(encoding="utf-8"))
