from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_phase25_review_modules_are_package_discoverable() -> None:
    review = ROOT / "src" / "intentforge" / "review"
    assert (review / "provenance.py").is_file()
    assert (review / "provenance_schema.py").is_file()
    assert (review / "diff_schema.py").is_file()


def test_phase25_core_contains_no_forbidden_execution_or_network_imports() -> None:
    review = ROOT / "src" / "intentforge" / "review"
    sources = "\n".join(
        (review / name).read_text(encoding="utf-8")
        for name in ("provenance.py", "provenance_schema.py", "comparison.py", "diff_schema.py")
    )
    forbidden = (
        "eval(",
        "exec(",
        "subprocess",
        "import_module",
        "__import__",
        "requests.",
        "httpx",
        "cadquery",
        "LLMProvider",
    )
    assert all(item not in sources for item in forbidden)
