from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAS_MODULE = ROOT / "src" / "intentforge" / "cas.py"


def test_cas_module_is_in_src_layout_package() -> None:
    assert CAS_MODULE.is_file()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["intentforge*", "mcp_server*", "benchmark*", "harness*"]' in pyproject


def test_cas_module_has_no_execution_network_or_llm_surface() -> None:
    source = CAS_MODULE.read_text(encoding="utf-8")
    for forbidden in (
        "eval(", "exec(", "importlib", "subprocess", "requests", "httpx", "urllib.request",
        "socket", "cadquery", "LLMProvider", "load_review_policies", "load_evidence_definitions",
    ):
        assert forbidden not in source


def test_cas_module_imports_only_standard_library_and_offline_verifier() -> None:
    tree = ast.parse(CAS_MODULE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert imported <= {
        "__future__", "dataclasses", "hashlib", "json", "os", "pathlib", "re", "shutil",
        "tempfile", "typing", "intentforge.offline_verify",
    }
