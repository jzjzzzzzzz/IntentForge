from importlib import resources

import tomllib


def test_pack_yaml_files_are_package_resources() -> None:
    data = resources.files("intentforge.knowledge.packs.data")
    names = sorted(path.name for path in data.iterdir() if path.name.endswith(".yaml"))

    assert names == ["assembly.yaml", "manufacturing.yaml", "mechanical.yaml", "structural.yaml"]


def test_pyproject_includes_pack_yaml_package_data() -> None:
    with open("pyproject.toml", "rb") as project_file:
        pyproject = tomllib.load(project_file)

    package_data = pyproject["tool"]["setuptools"]["package-data"]
    assert package_data["intentforge.knowledge.packs.data"] == ["*.yaml"]
