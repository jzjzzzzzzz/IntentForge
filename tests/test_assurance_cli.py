from pathlib import Path

from intentforge.cli import main


def test_assurance_cli_static_build_validate_and_package(tmp_path: Path) -> None:
    assert main(["assurance", "build", "--profile", "static", "--output-root", str(tmp_path)]) == 0
    case = tmp_path / "assurance" / "assurance_case.json"
    assert main(["assurance", "validate", str(case)]) == 0
    package = tmp_path / "package"
    assert main(["assurance", "package", str(case), "--output", str(package)]) == 0
    assert main(["assurance", "package-validate", str(package)]) == 0
    assert main(["assurance", "package-inspect", str(package), "--json"]) == 0


def test_assurance_cli_show_render_compare(tmp_path: Path) -> None:
    main(["assurance", "build", "--profile", "static", "--output-root", str(tmp_path)])
    case = tmp_path / "assurance" / "assurance_case.json"
    assert main(["assurance", "show", str(case), "--json"]) == 0
    assert main(["assurance", "render", str(case), "--output", str(tmp_path / "rendered.md")]) == 0
    assert main(["assurance", "compare", str(case), str(case), "--json"]) == 0
