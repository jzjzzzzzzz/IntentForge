import json

from intentforge.cli import main


def test_evidence_list_cli(capsys) -> None:
    assert main(["knowledge", "evidence-list", "--family", "l_bracket"]) == 0
    output = capsys.readouterr().out
    assert "Engineering Evidence Definitions" in output
    assert "l_bracket" in output


def test_evidence_list_json_cli(capsys) -> None:
    assert main(["knowledge", "evidence-list", "--json", "--role", "verification"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload
    assert all(item["role"] == "verification" for item in payload)


def test_evidence_show_cli(capsys) -> None:
    assert main(["knowledge", "evidence-show", "ev_package_evidence_manifest"]) == 0
    output = capsys.readouterr().out
    assert "ev_package_evidence_manifest" in output


def test_evidence_validate_and_resolve_cli(capsys) -> None:
    assert main(["knowledge", "evidence-validate"]) == 0
    assert "PASS" in capsys.readouterr().out
    assert main(["knowledge", "evidence-resolve"]) == 0
    assert "Engineering Evidence Resolution" in capsys.readouterr().out


def test_evidence_bundles_and_trust_cli(capsys) -> None:
    assert main(["knowledge", "evidence-bundles", "--family", "wall_mounted_bracket"]) == 0
    assert "Engineering Evidence Bundles" in capsys.readouterr().out
    assert main(["knowledge", "trust-report"]) == 0
    assert "Engineering Evidence Trust Report" in capsys.readouterr().out
    assert main(["knowledge", "trust-report", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["overall_trust_gate_passed"] is True
    assert main(["knowledge", "trust-validate"]) == 0
