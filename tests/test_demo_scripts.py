"""Tests for IntentForge product demo scripts.

These tests verify that the demo scripts:
- Import cleanly
- Handle missing httpx gracefully
- Handle server-unreachable gracefully (via mock)
- Contain the expected step functions

No live server is required — all API calls are mocked via httpx.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Import safety ────────────────────────────────────────────────────


def test_api_client_demo_imports():
    """api_client_demo.py should import without errors when httpx is available."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "api_client_demo",
        "examples/api_client_demo.py",
    )
    mod = importlib.util.module_from_spec(spec)
    # httpx is available in the test environment
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
    assert hasattr(mod, "step_health")
    assert hasattr(mod, "step_parse_build_dry")
    assert hasattr(mod, "step_parse_build_full")
    assert hasattr(mod, "step_edit_apply_dry")
    assert hasattr(mod, "step_edit_apply_full")


def test_product_workflow_demo_imports():
    """product_workflow_demo.py should import without errors when httpx is available."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "product_workflow_demo",
        "examples/product_workflow_demo.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "main")
    assert hasattr(mod, "workflow_connectivity")
    assert hasattr(mod, "workflow_parse_intent")
    assert hasattr(mod, "workflow_dry_run")
    assert hasattr(mod, "workflow_full_build")
    assert hasattr(mod, "workflow_edit_dry")
    assert hasattr(mod, "workflow_edit_full")
    assert hasattr(mod, "workflow_rejection")
    assert hasattr(mod, "workflow_artifact_list")


def test_api_client_demo_missing_httpx():
    """api_client_demo should exit with a clear message if httpx is missing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "api_client_demo_no_httpx",
        "examples/api_client_demo.py",
    )
    mod = importlib.util.module_from_spec(spec)

    # Temporarily hide httpx
    real_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = None  # type: ignore[assignment]

    with pytest.raises(SystemExit) as exc_info:
        spec.loader.exec_module(mod)

    # Restore httpx
    if real_httpx is not None:
        sys.modules["httpx"] = real_httpx
    else:
        del sys.modules["httpx"]

    assert exc_info.value.code == 1


def test_product_workflow_demo_missing_httpx():
    """product_workflow_demo should exit with a clear message if httpx is missing."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "product_workflow_demo_no_httpx",
        "examples/product_workflow_demo.py",
    )
    mod = importlib.util.module_from_spec(spec)

    real_httpx = sys.modules.get("httpx")
    sys.modules["httpx"] = None  # type: ignore[assignment]

    with pytest.raises(SystemExit) as exc_info:
        spec.loader.exec_module(mod)

    if real_httpx is not None:
        sys.modules["httpx"] = real_httpx
    else:
        del sys.modules["httpx"]

    assert exc_info.value.code == 1


# ── Mocked API calls ─────────────────────────────────────────────────


_MOCK_HEALTH = {"status": "ok", "service": "IntentForge API"}

_MOCK_PARSE = {
    "ok": True,
    "request_id": "req_mock_parse_001",
    "operation": "parse",
    "object_type": "wall_mounted_bracket",
    "validation": {"valid": True, "total_checks": 8, "passed_checks": 8, "failed_checks": 0},
    "artifacts": [],
}

_MOCK_PARSE_BUILD_DRY = {
    "ok": True,
    "request_id": "req_mock_dry_002",
    "operation": "parse_build",
    "object_type": "wall_mounted_bracket",
    "dry_run": True,
    "cad_exported": False,
    "validation": {"valid": True, "total_checks": 8, "passed_checks": 8, "failed_checks": 0},
    "artifacts": [],
}

_MOCK_PARSE_BUILD_FULL = {
    "ok": True,
    "request_id": "req_mock_full_003",
    "operation": "parse_build",
    "object_type": "wall_mounted_bracket",
    "dry_run": False,
    "cad_exported": True,
    "run_id": "run_mock_001",
    "validation": {"valid": True, "total_checks": 8, "passed_checks": 8, "failed_checks": 0},
    "artifacts": [
        {"kind": "step", "path": "output/.../bracket.step", "description": "STEP export"},
        {"kind": "stl", "path": "output/.../bracket.stl", "description": "STL export"},
    ],
}

_MOCK_EDIT_DRY = {
    "ok": True,
    "request_id": "req_mock_edit_dry_004",
    "operation": "edit_apply",
    "object_type": "wall_mounted_bracket",
    "dry_run": True,
    "cad_exported": False,
    "validation": {"valid": True, "total_checks": 8, "passed_checks": 8, "failed_checks": 0},
    "artifacts": [],
}

_MOCK_EDIT_FULL = {
    "ok": True,
    "request_id": "req_mock_edit_full_005",
    "operation": "edit_apply",
    "object_type": "wall_mounted_bracket",
    "dry_run": False,
    "cad_exported": True,
    "validation": {"valid": True, "total_checks": 8, "passed_checks": 8, "failed_checks": 0},
    "artifacts": [
        {"kind": "step", "path": "output/.../edited_bracket.step", "description": "STEP export"},
    ],
}

_MOCK_REJECTION = {
    "ok": False,
    "request_id": "req_mock_reject_006",
    "operation": "parse_build",
    "error_type": "UnsupportedGeometryError",
    "message": "Three mounting holes is not a supported pattern.",
    "error": {
        "error_type": "UnsupportedGeometryError",
        "message": "Three mounting holes is not a supported pattern.",
        "recoverable": True,
    },
    "cad_exported": False,
    "artifacts": [],
}

_MOCK_RUN_METADATA = {
    "ok": True,
    "request_id": "req_mock_run_007",
    "run_id": "run_mock_001",
    "operation": "get_run_metadata",
    "artifacts": [
        {"kind": "intent_json", "path": "output/.../intent.json"},
    ],
}


def _make_mock_client(responses: dict[str, dict]) -> MagicMock:
    """Create a mock httpx.Client that returns pre-configured responses."""

    client = MagicMock()

    def _get(path, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = responses.get(path, {"ok": True})
        return mock_resp

    def _post(path, json=None, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Return the appropriate mock based on endpoint + payload
        if "/v1/parse-build" in path and json and json.get("dry_run"):
            mock_resp.json.return_value = responses.get("/v1/parse-build/dry", _MOCK_PARSE_BUILD_DRY)
        elif "/v1/parse-build" in path:
            mock_resp.json.return_value = responses.get("/v1/parse-build/full", _MOCK_PARSE_BUILD_FULL)
        elif "/v1/parse" in path and "/v1/parse-build" not in path:
            mock_resp.json.return_value = responses.get("/v1/parse", _MOCK_PARSE)
        elif "/v1/edit-apply" in path and json and json.get("dry_run"):
            mock_resp.json.return_value = responses.get("/v1/edit-apply/dry", _MOCK_EDIT_DRY)
        elif "/v1/edit-apply" in path:
            mock_resp.json.return_value = responses.get("/v1/edit-apply/full", _MOCK_EDIT_FULL)
        else:
            mock_resp.json.return_value = responses.get(path, {"ok": True})
        return mock_resp

    client.get = _get
    client.post = _post
    client.close = MagicMock()
    return client


class TestApiClientDemoMocked:
    """Run api_client_demo steps with a mocked httpx.Client."""

    def test_step_health(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "api_client_demo_test",
            "examples/api_client_demo.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = _make_mock_client({"/health": _MOCK_HEALTH})
        mod.step_health(client)  # Should pass (asserts status 200 and ok)

    def test_step_parse_build_dry(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "api_client_demo_test2",
            "examples/api_client_demo.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = _make_mock_client({})
        mod.step_parse_build_dry(client)  # Asserts ok=True, dry_run=True, cad_exported=False

    def test_step_edit_apply_dry(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "api_client_demo_test3",
            "examples/api_client_demo.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = _make_mock_client({})
        mod.step_edit_apply_dry(client)  # Asserts ok=True, dry_run=True


class TestProductWorkflowDemoMocked:
    """Run product_workflow_demo steps with a mocked httpx.Client."""

    def test_workflow_connectivity_ok(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "product_workflow_demo_test",
            "examples/product_workflow_demo.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = _make_mock_client({"/health": _MOCK_HEALTH})
        result = mod.workflow_connectivity(client)
        assert result is True

    def test_workflow_connectivity_fail(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "product_workflow_demo_test2",
            "examples/product_workflow_demo.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = MagicMock()
        client.get.side_effect = __import__("httpx").ConnectError("no server")
        result = mod.workflow_connectivity(client)
        assert result is False

    def test_workflow_parse_intent(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "product_workflow_demo_test3",
            "examples/product_workflow_demo.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = _make_mock_client({"/v1/parse": _MOCK_PARSE})
        result = mod.workflow_parse_intent(client)
        assert result.get("ok") is True

    def test_workflow_dry_run(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "product_workflow_demo_test4",
            "examples/product_workflow_demo.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = _make_mock_client({})
        result = mod.workflow_dry_run(client)
        assert result.get("ok") is True
        assert result.get("dry_run") is True

    def test_workflow_rejection(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "product_workflow_demo_test5",
            "examples/product_workflow_demo.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_REJECTION
        client.post.return_value = mock_resp
        result = mod.workflow_rejection(client)
        assert result.get("ok") is False
        assert result.get("error", {}).get("error_type") == "UnsupportedGeometryError"
