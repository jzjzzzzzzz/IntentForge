from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "src" / "intentforge" / "offline_verify.py"


def test_offline_verifier_is_packaged_by_src_layout() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["intentforge*", "mcp_server*", "benchmark*", "harness*"]' in pyproject
    assert MODULE.is_file()


def test_offline_verifier_has_only_standard_library_imports() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= {
        "__future__", "dataclasses", "hashlib", "json", "os", "pathlib", "re", "typing", "urllib"
    }


def test_offline_verifier_contains_no_forbidden_execution_or_network_surface() -> None:
    source = MODULE.read_text(encoding="utf-8")
    for forbidden in (
        "eval(", "exec(", "importlib", "subprocess", "requests", "httpx", "urllib.request",
        "socket", "cadquery", "LLMProvider", "load_review_policies", "load_evidence_definitions",
    ):
        assert forbidden not in source
