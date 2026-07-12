"""Deterministic Merkle tree implementation for release dossier aggregation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


MERKLE_TREE_VERSION = "1.0"
MERKLE_HASH_ALGORITHM = "sha256"
_LEAF_DOMAIN_TAG = b"INTENTFORGE_DOSSIER_LEAF_V1\n"
_INTERNAL_DOMAIN_TAG = b"INTENTFORGE_DOSSIER_NODE_V1\n"
_EMPTY_TREE_HASH = "sha256:" + hashlib.sha256(
    b"INTENTFORGE_DOSSIER_EMPTY_V1\n"
).hexdigest()


@dataclass(frozen=True)
class MerkleNode:
    """A node in the deterministic Merkle tree."""

    level: int
    index: int
    hash_value: str
    left_hash: str | None = None
    right_hash: str | None = None
    is_leaf: bool = False
    leaf_content_address: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "level": self.level,
            "index": self.index,
            "hash": self.hash_value,
            "is_leaf": self.is_leaf,
        }
        if self.leaf_content_address is not None:
            data["leaf_content_address"] = self.leaf_content_address
        if self.left_hash is not None:
            data["left"] = self.left_hash
        if self.right_hash is not None:
            data["right"] = self.right_hash
        return data


@dataclass(frozen=True)
class MerkleTree:
    """Deterministic binary Merkle tree over content-addressed leaves."""

    leaves: tuple[str, ...]
    nodes: tuple[MerkleNode, ...]
    root_hash: str | None
    leaf_index_by_address: dict[str, int] = field(default_factory=dict)

    @property
    def leaf_count(self) -> int:
        return len(self.leaves)

    @property
    def height(self) -> int:
        if self.root_hash is None:
            return 0
        return _height_for_leaf_count(self.leaf_count)

    def to_dict(self) -> dict[str, Any]:
        return {
            "merkle_tree_version": MERKLE_TREE_VERSION,
            "hash_algorithm": MERKLE_HASH_ALGORITHM,
            "leaf_count": self.leaf_count,
            "height": self.height,
            "root_hash": self.root_hash,
            "leaves": list(self.leaves),
            "nodes": [node.to_dict() for node in self.nodes],
        }


def _height_for_leaf_count(leaf_count: int) -> int:
    if leaf_count <= 0:
        return 0
    height = 0
    n = leaf_count
    while n > 1:
        n = (n + 1) // 2
        height += 1
    return height


def _leaf_hash(content_address: str) -> str:
    canonical = json.dumps(
        {"content_address": content_address},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    payload = _LEAF_DOMAIN_TAG + canonical.encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _internal_hash(left_hash: str, right_hash: str) -> str:
    canonical = json.dumps(
        {"left": left_hash, "right": right_hash},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    payload = _INTERNAL_DOMAIN_TAG + canonical.encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def build_merkle_tree(content_addresses: tuple[str, ...] | list[str]) -> MerkleTree:
    """Build a deterministic Merkle tree over the given content addresses.

    Leaves are sorted by their content address prior to construction so that
    the resulting root hash is independent of caller ordering.
    """

    if not content_addresses:
        return MerkleTree(
            leaves=tuple(),
            nodes=tuple(),
            root_hash=None,
            leaf_index_by_address={},
        )

    sorted_leaves = tuple(sorted(set(content_addresses)))
    if len(sorted_leaves) != len(content_addresses):
        raise ValueError("duplicate content address in Merkle leaf set")

    nodes: list[MerkleNode] = []
    leaf_index_by_address: dict[str, int] = {}

    current_level_hashes: list[str] = []
    for index, address in enumerate(sorted_leaves):
        leaf_hash_value = _leaf_hash(address)
        leaf_index_by_address[address] = index
        nodes.append(MerkleNode(
            level=0,
            index=index,
            hash_value=leaf_hash_value,
            is_leaf=True,
            leaf_content_address=address,
        ))
        current_level_hashes.append(leaf_hash_value)

    if len(current_level_hashes) == 1:
        return MerkleTree(
            leaves=sorted_leaves,
            nodes=tuple(nodes),
            root_hash=current_level_hashes[0],
            leaf_index_by_address=leaf_index_by_address,
        )

    level = 1
    current_hashes = current_level_hashes
    while len(current_hashes) > 1:
        next_hashes: list[str] = []
        index = 0
        i = 0
        while i < len(current_hashes):
            left = current_hashes[i]
            right = current_hashes[i + 1] if i + 1 < len(current_hashes) else left
            node_hash = _internal_hash(left, right)
            nodes.append(MerkleNode(
                level=level,
                index=index,
                hash_value=node_hash,
                left_hash=left,
                right_hash=right,
            ))
            next_hashes.append(node_hash)
            index += 1
            i += 2
        current_hashes = next_hashes
        level += 1

    return MerkleTree(
        leaves=sorted_leaves,
        nodes=tuple(nodes),
        root_hash=current_hashes[0],
        leaf_index_by_address=leaf_index_by_address,
    )


def rebuild_merkle_root(content_addresses: tuple[str, ...] | list[str]) -> str | None:
    """Recompute the Merkle root hash from the supplied content addresses."""

    if not content_addresses:
        return None
    tree = build_merkle_tree(content_addresses)
    return tree.root_hash


def merkle_inclusion_proof(
    tree: MerkleTree, leaf_content_address: str,
) -> tuple[list[tuple[str, str]], ...] | None:
    """Build an inclusion proof for a leaf inside the tree.

    Returns a tuple of (sibling_hash, position) pairs where position is
    either "left" or "right".
    """

    if leaf_content_address not in tree.leaf_index_by_address:
        return None

    leaf_index = tree.leaf_index_by_address[leaf_content_address]
    nodes_by_level: dict[int, dict[int, MerkleNode]] = {}
    for node in tree.nodes:
        nodes_by_level.setdefault(node.level, {})[node.index] = node

    proof: list[tuple[str, str]] = []
    current_index = leaf_index
    for level in range(tree.height):
        nodes_at_level = nodes_by_level[level]
        current_node = nodes_at_level[current_index]
        is_right = current_index % 2 == 1
        sibling_index = current_index - 1 if is_right else current_index + 1
        sibling_node = nodes_at_level.get(sibling_index)
        if sibling_node is None:
            sibling_hash = current_node.hash_value
        else:
            sibling_hash = sibling_node.hash_value
        proof.append((sibling_hash, "left" if is_right else "right"))
        current_index = current_index // 2
    return tuple(proof)


def verify_merkle_inclusion_proof(
    leaf_content_address: str,
    root_hash: str,
    proof: tuple[tuple[str, str], ...] | list[tuple[str, str]],
) -> bool:
    """Verify an inclusion proof for a leaf against a Merkle root."""

    current = _leaf_hash(leaf_content_address)
    for sibling_hash, position in proof:
        if position == "left":
            current = _internal_hash(sibling_hash, current)
        elif position == "right":
            current = _internal_hash(current, sibling_hash)
        else:
            raise ValueError(f"invalid proof position: {position}")
    return current == root_hash