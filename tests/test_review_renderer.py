from intentforge.review import evaluate_assurance_case, get_review_policy, render_review_decision_markdown
from tests.review_test_helpers import rejection_case, static_case


def test_renderer_is_deterministic_and_has_required_sections() -> None:
    decision = evaluate_assurance_case(get_review_policy("intentforge_static_review_v1"), static_case())
    first = render_review_decision_markdown(decision)
    assert first == render_review_decision_markdown(decision)
    for section in ("Policy Applied", "Final Decision", "Checks Passed", "Conditions", "Known Limitations", "Review Notice", "Decision Identity"):
        assert f"## {section}" in first


def test_safe_rejection_wording_does_not_accept_design() -> None:
    decision = evaluate_assurance_case(get_review_policy("intentforge_safe_rejection_review_v1"), rejection_case())
    markdown = render_review_decision_markdown(decision)
    assert "Safe rejection handling passed policy" in markdown
    assert "unsupported design remains rejected" in markdown


def test_renderer_avoids_certification_and_guarantee_claims() -> None:
    decision = evaluate_assurance_case(get_review_policy("intentforge_static_review_v1"), static_case())
    markdown = render_review_decision_markdown(decision).lower()
    assert "certified safe" not in markdown
    assert "guaranteed manufacturable" not in markdown
    assert "/tmp/" not in markdown
