from intentforge.assurance import build_assurance_from_prompt, render_assurance_markdown


def test_renderer_is_deterministic_and_scoped() -> None:
    case = build_assurance_from_prompt(profile="static")
    first = render_assurance_markdown(case)
    assert first == render_assurance_markdown(case)
    for heading in ("Design Request", "Assurance Claims", "Known Limitations", "Review Requirements"):
        assert heading in first
    assert "certified safe" not in first.lower()
    assert "trust score" not in first.lower()
