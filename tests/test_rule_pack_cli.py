from intentforge.cli import main


def test_knowledge_packs_cli(capsys) -> None:
    result = main(["knowledge", "packs"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Engineering Knowledge Rule Packs" in output
    assert "bracket_mechanical" in output
    assert "Total active rules: 10" in output


def test_knowledge_packs_validate_cli(capsys) -> None:
    result = main(["knowledge", "packs-validate"])

    output = capsys.readouterr().out
    assert result == 0
    assert "Knowledge rule pack validation" in output
    assert "PASS" in output
    assert "4 packs checked" in output
    assert "10 rules checked" in output
    assert "0 errors" in output
