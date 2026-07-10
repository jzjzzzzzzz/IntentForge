from intentforge.knowledge.evidence_bundles import build_all_evidence_bundles


def test_one_bundle_per_capability() -> None:
    bundles = build_all_evidence_bundles()
    assert len(bundles) == 28
    assert {bundle.capability_id for bundle in bundles}


def test_bundle_ids_are_deterministic() -> None:
    first = build_all_evidence_bundles()
    second = build_all_evidence_bundles()
    assert [bundle.bundle_id for bundle in first] == [bundle.bundle_id for bundle in second]


def test_family_and_capability_filters() -> None:
    l_bundles = build_all_evidence_bundles(family="l_bracket")
    one = build_all_evidence_bundles(capability_id="wall_center_cutout")
    assert l_bundles
    assert all(bundle.family == "l_bracket" for bundle in l_bundles)
    assert len(one) == 1
    assert one[0].capability_id == "wall_center_cutout"
