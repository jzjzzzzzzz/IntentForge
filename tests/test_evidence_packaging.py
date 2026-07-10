from importlib import resources


def test_evidence_manifest_packaged() -> None:
    assert resources.files("intentforge.knowledge.data").joinpath("evidence_manifest.yaml").is_file()


def test_rule_pack_and_capability_manifests_still_packaged() -> None:
    assert resources.files("intentforge.knowledge.data").joinpath("capability_manifest.yaml").is_file()
    assert resources.files("intentforge.knowledge.packs.data").joinpath("mechanical.yaml").is_file()
