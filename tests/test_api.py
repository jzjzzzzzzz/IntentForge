"""Tests for IntentForge optional HTTP API layer.

These tests gracefully skip when FastAPI/httpx are not installed,
so core tests continue to work without the ``api`` optional extra.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any
import unittest

# ── Skip guard ──────────────────────────────────────────────────────

try:
    import fastapi  # noqa: F401
    import httpx  # noqa: F401
    from fastapi.testclient import TestClient  # noqa: F401
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

import pytest

skip_no_fastapi = pytest.mark.skipif(
    not FASTAPI_AVAILABLE,
    reason="FastAPI and httpx are required for API tests. Install with: pip install -e '.[api]'",
)


# ── Global state reset fixture ──────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_auth_state():
    """Reset optional_token_auth singleton state before each test."""
    from intentforge.api.security import optional_token_auth
    optional_token_auth._enabled = False
    optional_token_auth._token = None
    os.environ.pop("INTENTFORGE_API_TOKEN", None)
    yield
    optional_token_auth._enabled = False
    optional_token_auth._token = None
    os.environ.pop("INTENTFORGE_API_TOKEN", None)
    os.environ.pop("INTENTFORGE_LLM_PROVIDER", None)


# ── Helpers ──────────────────────────────────────────────────────────

def _create_test_client(token: str | None = None) -> "TestClient":
    """Create a TestClient with optional auth token."""

    # Reset auth state before each test.
    from intentforge.api.security import optional_token_auth
    optional_token_auth._enabled = False
    optional_token_auth._token = None

    if token:
        os.environ["INTENTFORGE_API_TOKEN"] = token
    else:
        os.environ.pop("INTENTFORGE_API_TOKEN", None)

    from intentforge.api.app import create_app
    app = create_app()
    return TestClient(app)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── Health endpoint ──────────────────────────────────────────────────

@skip_no_fastapi
class TestHealthEndpoint:
    """Tests for GET /health."""

    def test_health_no_auth(self):
        """Health endpoint should work without auth even when auth is enabled."""
        client = _create_test_client(token="test-secret")
        # Health endpoint is excluded from auth dependencies.
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "IntentForge API"

    def test_health_no_token_configured(self):
        client = _create_test_client(token=None)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


# ── Auth behavior ────────────────────────────────────────────────────

@skip_no_fastapi
class TestAuthBehavior:
    """Tests for optional Bearer token authentication."""

    def test_no_auth_allows_access(self):
        """When INTENTFORGE_API_TOKEN is not set, all endpoints are open."""
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse",
            json={"prompt": "A wall-mounted bracket 100mm wide 60mm tall 3mm thick"},
        )
        assert response.status_code == 200

    def test_auth_required_when_token_set(self):
        """When INTENTFORGE_API_TOKEN is set, endpoints require Bearer token."""
        client = _create_test_client(token="my-secret-token")
        response = client.post(
            "/v1/parse",
            json={"prompt": "A wall-mounted bracket 100mm wide"},
        )
        assert response.status_code == 401

    def test_auth_valid_token(self):
        """Correct Bearer token allows access."""
        client = _create_test_client(token="my-secret-token")
        response = client.post(
            "/v1/parse",
            json={"prompt": "A wall-mounted bracket 100mm wide 60mm tall 3mm thick"},
            headers=_auth_header("my-secret-token"),
        )
        assert response.status_code == 200

    def test_auth_wrong_token(self):
        """Wrong Bearer token returns 401."""
        client = _create_test_client(token="my-secret-token")
        response = client.post(
            "/v1/parse",
            json={"prompt": "A bracket"},
            headers=_auth_header("wrong-token"),
        )
        assert response.status_code == 401

    def test_auth_malformed_header(self):
        """Malformed Authorization header returns 401."""
        client = _create_test_client(token="my-secret-token")
        response = client.post(
            "/v1/parse",
            json={"prompt": "A bracket"},
            headers={"Authorization": "Basic abc123"},
        )
        assert response.status_code == 401


# ── Parse endpoints ──────────────────────────────────────────────────

@skip_no_fastapi
class TestParseEndpoint:
    """Tests for POST /v1/parse."""

    def test_parse_valid_prompt(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse",
            json={"prompt": "A wall-mounted bracket 100mm wide 60mm tall 3mm thick"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "request_id" in data
        assert "intent" in data
        assert data["object_type"] == "wall_mounted_bracket"

    def test_parse_with_request_id(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse",
            json={
                "prompt": "A wall-mounted bracket 100mm wide",
                "request_id": "my-req-001",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["request_id"] == "my-req-001"

    def test_parse_unsupported_object(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse",
            json={"prompt": "A curved adjustable bracket"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["error"]["error_type"] == "UnsupportedObjectError"

    def test_parse_empty_prompt_rejected(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse",
            json={"prompt": ""},
        )
        # Pydantic validation rejects empty prompt.
        assert response.status_code == 422

    def test_parse_extra_fields_rejected(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse",
            json={"prompt": "A bracket", "unknown_field": "value"},
        )
        assert response.status_code == 422


# ── Parse-build endpoint ────────────────────────────────────────────

@skip_no_fastapi
class TestParseBuildEndpoint:
    """Tests for POST /v1/parse-build."""

    def test_parse_build_valid_prompt(self):
        """Parse-build should produce contract-compatible response."""
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse-build",
            json={"prompt": "A wall-mounted bracket 100mm wide 60mm tall 3mm thick"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert "operation" in data
        assert data["operation"] == "parse_build"

    def test_parse_build_dry_run(self):
        """Dry run should return result without exporting STEP/STL."""
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse-build",
            json={
                "prompt": "A wall-mounted bracket 100mm wide 60mm tall 3mm thick",
                "dry_run": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert data["cad_exported"] is False


# ── Edit endpoints ──────────────────────────────────────────────────

@skip_no_fastapi
class TestEditEndpoints:
    """Tests for POST /v1/edit-parse and /v1/edit-apply."""

    def test_edit_parse_valid(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/edit-parse",
            json={"edit_text": "Make it 150mm wide but keep the same thickness"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "edit_request" in data

    def test_edit_parse_rejected(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/edit-parse",
            json={"edit_text": "Make it curved"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False

    def test_edit_apply_valid(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/edit-apply",
            json={
                "target": "bracket",
                "edit_text": "Make it 150mm wide but keep the same thickness",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data

    def test_edit_apply_dry_run(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/edit-apply",
            json={
                "target": "bracket",
                "edit_text": "Make it 150mm wide but keep the same thickness",
                "dry_run": True,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True

    def test_edit_apply_unsupported_target(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/edit-apply",
            json={"target": "curved_bracket", "edit_text": "Make it wider"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False


# ── LLM endpoints ───────────────────────────────────────────────────

@skip_no_fastapi
class TestLlmEndpoints:
    """Tests for LLM translation endpoints (no real LLM provider)."""

    def test_llm_parse_no_provider(self):
        """LLM parse should return LLMProviderUnavailableError when no provider is set."""
        client = _create_test_client(token=None)
        os.environ.pop("INTENTFORGE_LLM_PROVIDER", None)
        response = client.post(
            "/v1/llm/parse",
            json={"prompt": "A bracket 100mm wide"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["error"]["error_type"] == "LLMProviderUnavailableError"

    def test_llm_parse_build_no_provider(self):
        client = _create_test_client(token=None)
        os.environ.pop("INTENTFORGE_LLM_PROVIDER", None)
        response = client.post(
            "/v1/llm/parse-build",
            json={"prompt": "A bracket"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["error"]["error_type"] == "LLMProviderUnavailableError"

    def test_llm_edit_parse_no_provider(self):
        client = _create_test_client(token=None)
        os.environ.pop("INTENTFORGE_LLM_PROVIDER", None)
        response = client.post(
            "/v1/llm/edit-parse",
            json={"object_type": "wall_mounted_bracket", "edit_text": "Make it wider"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["error"]["error_type"] == "LLMProviderUnavailableError"

    def test_llm_edit_apply_no_provider(self):
        client = _create_test_client(token=None)
        os.environ.pop("INTENTFORGE_LLM_PROVIDER", None)
        response = client.post(
            "/v1/llm/edit-apply",
            json={"object_type": "wall_mounted_bracket", "edit_text": "Make it wider"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["error"]["error_type"] == "LLMProviderUnavailableError"

    def test_llm_parse_with_mock_provider(self):
        """LLM parse with mock provider should return structured intent."""
        client = _create_test_client(token=None)
        os.environ["INTENTFORGE_LLM_PROVIDER"] = "mock"
        response = client.post(
            "/v1/llm/parse",
            json={"prompt": "A wall-mounted bracket 100mm wide"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        # Clean up.
        os.environ.pop("INTENTFORGE_LLM_PROVIDER", None)


# ── Runs endpoints ───────────────────────────────────────────────────

@skip_no_fastapi
class TestRunsEndpoints:
    """Tests for GET /v1/runs/recent and /v1/runs/{kind}/{run_id}."""

    def test_list_recent_runs_empty(self):
        client = _create_test_client(token=None)
        # Use a fresh output root with no runs.
        response = client.get(
            "/v1/runs/recent",
            params={"kind": "parsed_runs", "limit": 5, "output_root": "/tmp/intentforge_api_test_runs"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["runs"] == []

    def test_list_recent_runs_invalid_kind(self):
        client = _create_test_client(token=None)
        response = client.get(
            "/v1/runs/recent",
            params={"kind": "invalid_kind"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False

    def test_get_run_metadata_not_found(self):
        client = _create_test_client(token=None)
        response = client.get(
            "/v1/runs/parsed_runs/nonexistent_run_id",
            params={"output_root": "/tmp/intentforge_api_test_runs"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False


# ── Artifact safety ──────────────────────────────────────────────────

@skip_no_fastapi
class TestArtifactSafety:
    """Tests for path traversal rejection in artifact serving."""

    def test_path_traversal_rejected(self):
        """Percent-encoded path traversal (..) should be rejected with 403."""
        client = _create_test_client(token=None)
        # Starlette normalizes literal ../ in URLs before routing,
        # so use percent-encoded form to ensure it reaches the handler.
        response = client.get("/v1/artifacts/%2e%2e/etc/passwd")
        assert response.status_code == 403

    def test_absolute_path_rejected(self):
        """Absolute paths should be rejected."""
        client = _create_test_client(token=None)
        response = client.get("/v1/artifacts//etc/passwd")
        # Starlette normalizes double slashes, so this becomes /v1/artifacts/etc/passwd
        # which is just a nonexistent file under output → 404.
        assert response.status_code in {403, 404}

    def test_nonexistent_artifact_404(self):
        """Nonexistent files under output/ should return 404."""
        client = _create_test_client(token=None)
        response = client.get("/v1/artifacts/nonexistent_file.json")
        assert response.status_code == 404


# ── Contract compatibility ──────────────────────────────────────────

@skip_no_fastapi
class TestContractCompatibility:
    """Verify all API responses are contract-compatible ToolResponse envelopes."""

    def test_parse_response_contract_keys(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse",
            json={"prompt": "A wall-mounted bracket 100mm wide"},
        )
        assert response.status_code == 200
        data = response.json()
        # ToolResponse required keys.
        assert "ok" in data
        assert "request_id" in data
        assert "operation" in data
        assert "artifacts" in data

    def test_error_response_contract_keys(self):
        client = _create_test_client(token=None)
        response = client.post(
            "/v1/parse",
            json={"prompt": "A curved adjustable bracket"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert "error" in data
        assert data["error"]["error_type"] is not None
        assert data["error"]["message"] is not None


# ── Module-level import safety ──────────────────────────────────────

class TestImportSafety:
    """Verify API module imports don't break core when FastAPI is absent."""

    def test_api_module_init_importable(self):
        """intentforge.api.__init__ should be importable even without FastAPI."""
        import intentforge.api  # noqa: F401
        assert hasattr(intentforge.api, "create_app")
        assert hasattr(intentforge.api, "serve")

    def test_security_module_importable(self):
        """Security module should be importable without FastAPI."""
        from intentforge.api.security import OptionalTokenAuth, optional_token_auth
        assert optional_token_auth.is_enabled() is False

    def test_artifacts_module_importable(self):
        """Artifacts module should be importable without FastAPI."""
        from intentforge.api.artifacts import safe_artifact_path, OUTPUT_ROOT
        assert OUTPUT_ROOT is not None

    def test_schemas_module_importable(self):
        """Schemas module (Pydantic-only) should be importable without FastAPI."""
        from intentforge.api.schemas import ParseRequest, ParseBuildRequest
        req = ParseRequest(prompt="A bracket")
        assert req.prompt == "A bracket"


# ── Artifact path safety (no FastAPI needed) ────────────────────────

class TestArtifactPathSafety:
    """Unit tests for safe_artifact_path that don't require FastAPI."""

    def test_normal_path_accepted(self):
        from intentforge.api.artifacts import safe_artifact_path
        path = safe_artifact_path("parsed_bracket.step")
        assert str(path).endswith("parsed_bracket.step")

    def test_traversal_dotdot_rejected(self):
        from intentforge.api.artifacts import safe_artifact_path
        with pytest.raises(ValueError, match="traversal"):
            safe_artifact_path("../etc/passwd")

    def test_absolute_path_rejected(self):
        from intentforge.api.artifacts import safe_artifact_path
        with pytest.raises(ValueError, match="traversal"):
            safe_artifact_path("/etc/passwd")

    def test_windows_backslash_rejected(self):
        from intentforge.api.artifacts import safe_artifact_path
        with pytest.raises(ValueError, match="traversal"):
            safe_artifact_path("\\etc\\passwd")
