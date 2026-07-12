"""Phase 29: Cryptographic Merkle-tree algorithm tests."""

from __future__ import annotations

import hashlib
import json

import pytest

from intentforge.dossier.merkle import (
    MERKLE_TREE_VERSION,
    build_merkle_tree,
    merkle_inclusion_proof,
    rebuild_merkle_root,
    verify_merkle_inclusion_proof,
)


def _leaf_address(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def test_empty_tree_returns_none_root() -> None:
    tree = build_merkle_tree(())
    assert tree.root_hash is None
    assert tree.leaf_count == 0
    assert tree.height == 0
    assert rebuild_merkle_root(()) is None


def test_single_leaf_root_equals_leaf_hash() -> None:
    address = _leaf_address("only-leaf")
    tree = build_merkle_tree((address,))
    assert tree.leaf_count == 1
    assert tree.height == 0
    assert tree.root_hash is not None
    assert tree.root_hash.startswith("sha256:")
    leaf_node = tree.nodes[0]
    assert leaf_node.is_leaf is True
    assert leaf_node.leaf_content_address == address
    assert tree.root_hash == leaf_node.hash_value


def test_two_leaf_tree_uses_internal_node() -> None:
    a = _leaf_address("a")
    b = _leaf_address("b")
    tree = build_merkle_tree((a, b))
    assert tree.leaf_count == 2
    assert tree.height == 1
    leaves = {n.leaf_content_address: n for n in tree.nodes if n.is_leaf}
    assert set(leaves) == {a, b}


def test_tree_root_is_independent_of_input_order() -> None:
    leaves = [_leaf_address(f"leaf-{i}") for i in range(8)]
    forward = build_merkle_tree(tuple(leaves))
    reverse = build_merkle_tree(tuple(reversed(leaves)))
    mixed = build_merkle_tree(tuple(leaves[3:6] + leaves[0:3] + leaves[6:]))
    assert forward.root_hash == reverse.root_hash == mixed.root_hash


def test_merkle_root_changes_when_leaf_changes() -> None:
    leaves = [_leaf_address(f"leaf-{i}") for i in range(4)]
    tree1 = build_merkle_tree(tuple(leaves))
    leaves[1] = _leaf_address("tampered-leaf")
    tree2 = build_merkle_tree(tuple(leaves))
    assert tree1.root_hash != tree2.root_hash


def test_rebuild_root_matches_build_root() -> None:
    leaves = [_leaf_address(f"leaf-{i}") for i in range(16)]
    tree = build_merkle_tree(tuple(leaves))
    assert rebuild_merkle_root(tuple(leaves)) == tree.root_hash


def test_duplicate_leaf_address_raises() -> None:
    address = _leaf_address("dup")
    with pytest.raises(ValueError):
        build_merkle_tree((address, address))


def test_inclusion_proof_verifies_for_each_leaf() -> None:
    leaves = [_leaf_address(f"leaf-{i}") for i in range(8)]
    tree = build_merkle_tree(tuple(leaves))
    for address in leaves:
        proof = merkle_inclusion_proof(tree, address)
        assert proof is not None
        assert verify_merkle_inclusion_proof(address, tree.root_hash, proof)


def test_inclusion_proof_unknown_leaf_returns_none() -> None:
    leaves = [_leaf_address(f"leaf-{i}") for i in range(3)]
    tree = build_merkle_tree(tuple(leaves))
    missing = _leaf_address("not-in-tree")
    assert merkle_inclusion_proof(tree, missing) is None


def test_tampered_leaf_fails_inclusion_proof() -> None:
    leaves = [_leaf_address(f"leaf-{i}") for i in range(4)]
    tree = build_merkle_tree(tuple(leaves))
    tampered = _leaf_address("tampered")
    proof = merkle_inclusion_proof(tree, leaves[2])
    assert verify_merkle_inclusion_proof(tampered, tree.root_hash, proof) is False


def test_to_dict_is_serializable() -> None:
    leaves = [_leaf_address(f"leaf-{i}") for i in range(3)]
    tree = build_merkle_tree(tuple(leaves))
    payload = tree.to_dict()
    json.dumps(payload, sort_keys=True)
    assert payload["merkle_tree_version"] == MERKLE_TREE_VERSION
    assert payload["hash_algorithm"] == "sha256"
    assert payload["leaf_count"] == 3


def test_tree_height_for_powers_of_two() -> None:
    for n in [1, 2, 4, 8, 16]:
        leaves = [_leaf_address(f"leaf-{i}") for i in range(n)]
        tree = build_merkle_tree(tuple(leaves))
        expected_height = 0 if n == 1 else (n.bit_length() - 1)
        assert tree.height == expected_height, f"height for {n} should be {expected_height}"