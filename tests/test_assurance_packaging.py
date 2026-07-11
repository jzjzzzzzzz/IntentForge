from pathlib import Path


def test_assurance_modules_are_discoverable_by_setuptools() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "src" / "intentforge" / "assurance" / "__init__.py").is_file()
    assert "intentforge*" in (root / "pyproject.toml").read_text(encoding="utf-8")
