from intentforge.cli import main


def test_knowledge_coverage_cli(capsys) -> None:
    code = main(["knowledge", "coverage"])
    output = capsys.readouterr().out

    assert code == 0
    assert "Engineering Knowledge Coverage" in output
    assert "Declared capabilities: 28" in output
    assert "Orphan active rules: 0" in output


def test_knowledge_coverage_json_cli(capsys) -> None:
    code = main(["knowledge", "coverage", "--json"])
    output = capsys.readouterr().out

    assert code == 0
    assert '"declared_capability_count": 28' in output
    assert '"passed": true' in output


def test_coverage_validate_cli(capsys) -> None:
    code = main(["knowledge", "coverage-validate"])
    output = capsys.readouterr().out

    assert code == 0
    assert "Engineering capability validation" in output
    assert "PASS" in output


def test_capability_validate_alias_cli(capsys) -> None:
    code = main(["knowledge", "capability-validate"])
    output = capsys.readouterr().out

    assert code == 0
    assert "Engineering capability validation" in output


def test_capability_matrix_cli_filter(capsys) -> None:
    code = main(["knowledge", "capability-matrix", "--family", "l_bracket", "--status", "unsupported"])
    output = capsys.readouterr().out

    assert code == 0
    assert "Engineering Capability Matrix" in output
    assert "l_four_hole_pattern" in output
    assert "wall_" not in output


def test_capability_matrix_json_cli(capsys) -> None:
    code = main(["knowledge", "capability-matrix", "--json", "--stage", "engineering_reasoning"])
    output = capsys.readouterr().out

    assert code == 0
    assert '"matrix_id"' in output
    assert '"engineering_reasoning"' in output
