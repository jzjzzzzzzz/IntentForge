from reasoning_test_helpers import reasoning_report


def test_reinforcing_interaction_detected() -> None:
    report = reasoning_report(["cutout_stiffness_tradeoff_001", "thin_section_warning_001"])

    assert "reinforces" in {interaction.interaction_type for interaction in report.interactions}


def test_conflict_interaction_detected() -> None:
    report = reasoning_report(["hole_edge_margin_001", "hole_spacing_001"])

    assert "conflicts" in {interaction.interaction_type for interaction in report.interactions}


def test_mitigation_interaction_detected() -> None:
    report = reasoning_report(["thin_section_warning_001"], model_family="l_bracket")

    assert "mitigates" in {interaction.interaction_type for interaction in report.interactions}


def test_unsupported_interaction_not_invented() -> None:
    report = reasoning_report(["hole_edge_margin_001"])

    assert report.interactions == []
