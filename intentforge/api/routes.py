"""FastAPI route registration for IntentForge HTTP API.

All endpoints return contract-compatible ToolResponse envelopes.
Routes are registered via ``register_routes(app)`` so the app factory
remains clean and testable.
"""

from typing import Any

from intentforge.api.security import auth_dependency
from intentforge.contracts import error_response, ensure_request_id


def register_routes(app: "fastapi.FastAPI") -> None:
    """Register all IntentForge API routes on the given FastAPI app."""

    from fastapi import Depends, HTTPException, Query
    from fastapi.responses import JSONResponse

    from intentforge.api.schemas import (
        EditApplyRequest,
        EditParseRequest,
        LlmEditApplyRequest,
        LlmEditParseRequest,
        LlmParseBuildRequest,
        LlmParseRequest,
        ParseBuildRequest,
        ParseRequest,
        TechnicalHarnessRequest,
    )
    from intentforge.api.artifacts import safe_artifact_path, serve_artifact_file
    from intentforge.llm import (
        LLMProviderUnavailableError,
        load_provider_from_env,
        translate_edit_apply,
        translate_edit_to_request,
        translate_prompt_to_build,
        translate_prompt_to_intent,
    )
    from intentforge.workflows import (
        edit_parse_apply_workflow,
        edit_parse_workflow,
        get_run_metadata_workflow,
        list_recent_runs_workflow,
        parse_build_workflow,
        parse_prompt_workflow,
        SUPPORTED_RUN_KINDS,
    )

    auth = auth_dependency()

    # ── Health ────────────────────────────────────────────────────

    @app.get("/health", tags=["system"])
    async def health_check():
        """Return API health status."""
        return {"status": "ok", "service": "IntentForge API"}

    # ── Deterministic CAD endpoints ───────────────────────────────

    @app.post("/v1/parse", tags=["cad"], dependencies=[auth] if auth else [])
    async def parse_endpoint(req: ParseRequest) -> dict[str, Any]:
        """Parse a deterministic CAD prompt into structured intent + parameters."""
        request_id = ensure_request_id(req.request_id)
        return parse_prompt_workflow(
            req.prompt,
            req.output_root,
            request_id=request_id,
        )

    @app.post("/v1/parse-build", tags=["cad"], dependencies=[auth] if auth else [])
    async def parse_build_endpoint(req: ParseBuildRequest) -> dict[str, Any]:
        """Parse a prompt, build CAD, export STEP/STL, and validate."""
        request_id = ensure_request_id(req.request_id)
        return parse_build_workflow(
            req.prompt,
            req.output_root,
            request_id=request_id,
            dry_run=req.dry_run,
        )

    @app.post("/v1/edit-parse", tags=["cad"], dependencies=[auth] if auth else [])
    async def edit_parse_endpoint(req: EditParseRequest) -> dict[str, Any]:
        """Parse a natural-language edit request into structured edit JSON."""
        request_id = ensure_request_id(req.request_id)
        return edit_parse_workflow(
            req.edit_text,
            req.output_root,
            request_id=request_id,
        )

    @app.post("/v1/edit-apply", tags=["cad"], dependencies=[auth] if auth else [])
    async def edit_apply_endpoint(req: EditApplyRequest) -> dict[str, Any]:
        """Parse and apply an edit to a bundled bracket/L-bracket example."""
        request_id = ensure_request_id(req.request_id)
        return edit_parse_apply_workflow(
            req.target,
            req.edit_text,
            req.output_root,
            request_id=request_id,
            dry_run=req.dry_run,
        )

    # ── LLM translation endpoints ─────────────────────────────────

    @app.post("/v1/llm/parse", tags=["llm"], dependencies=[auth] if auth else [])
    async def llm_parse_endpoint(req: LlmParseRequest) -> dict[str, Any]:
        """LLM-translate a CAD prompt into guarded IntentForge intent JSON."""
        request_id = ensure_request_id(req.request_id)
        try:
            provider = load_provider_from_env()
        except LLMProviderUnavailableError as exc:
            return error_response(
                operation="llm_parse",
                request_id=request_id,
                error_type="LLMProviderUnavailableError",
                message=str(exc),
                recoverable=True,
            )
        if provider is None:
            return error_response(
                operation="llm_parse",
                request_id=request_id,
                error_type="LLMProviderUnavailableError",
                message="No LLM provider is configured.",
                recoverable=True,
                suggested_action="Set INTENTFORGE_LLM_PROVIDER or use deterministic /v1/parse.",
            )
        return translate_prompt_to_intent(req.prompt, provider, request_id=request_id)

    @app.post("/v1/llm/parse-build", tags=["llm"], dependencies=[auth] if auth else [])
    async def llm_parse_build_endpoint(req: LlmParseBuildRequest) -> dict[str, Any]:
        """LLM-translate a prompt, guard it, build through deterministic CAD, and validate."""
        request_id = ensure_request_id(req.request_id)
        try:
            provider = load_provider_from_env()
        except LLMProviderUnavailableError as exc:
            return error_response(
                operation="llm_parse_build",
                request_id=request_id,
                error_type="LLMProviderUnavailableError",
                message=str(exc),
                recoverable=True,
            )
        if provider is None:
            return error_response(
                operation="llm_parse_build",
                request_id=request_id,
                error_type="LLMProviderUnavailableError",
                message="No LLM provider is configured.",
                recoverable=True,
            )
        return translate_prompt_to_build(
            req.prompt,
            provider,
            req.output_root,
            request_id=request_id,
            dry_run=req.dry_run,
        )

    @app.post("/v1/llm/edit-parse", tags=["llm"], dependencies=[auth] if auth else [])
    async def llm_edit_parse_endpoint(req: LlmEditParseRequest) -> dict[str, Any]:
        """LLM-translate an edit into guarded IntentForge edit JSON."""
        request_id = ensure_request_id(req.request_id)
        try:
            provider = load_provider_from_env()
        except LLMProviderUnavailableError as exc:
            return error_response(
                operation="llm_edit_parse",
                request_id=request_id,
                error_type="LLMProviderUnavailableError",
                message=str(exc),
                recoverable=True,
            )
        if provider is None:
            return error_response(
                operation="llm_edit_parse",
                request_id=request_id,
                error_type="LLMProviderUnavailableError",
                message="No LLM provider is configured.",
                recoverable=True,
            )
        return translate_edit_to_request(
            req.edit_text, req.object_type, provider, request_id=request_id
        )

    @app.post("/v1/llm/edit-apply", tags=["llm"], dependencies=[auth] if auth else [])
    async def llm_edit_apply_endpoint(req: LlmEditApplyRequest) -> dict[str, Any]:
        """LLM-translate an edit, guard it, then apply through deterministic CAD workflows."""
        request_id = ensure_request_id(req.request_id)
        try:
            provider = load_provider_from_env()
        except LLMProviderUnavailableError as exc:
            return error_response(
                operation="llm_edit_apply",
                request_id=request_id,
                error_type="LLMProviderUnavailableError",
                message=str(exc),
                recoverable=True,
            )
        if provider is None:
            return error_response(
                operation="llm_edit_apply",
                request_id=request_id,
                error_type="LLMProviderUnavailableError",
                message="No LLM provider is configured.",
                recoverable=True,
            )
        return translate_edit_apply(
            req.edit_text,
            req.object_type,
            provider,
            req.output_root,
            request_id=request_id,
            dry_run=req.dry_run,
        )

    # ── Harness & inspection ──────────────────────────────────────

    @app.post("/v1/technical-harness", tags=["harness"], dependencies=[auth] if auth else [])
    async def technical_harness_endpoint(req: TechnicalHarnessRequest) -> dict[str, Any]:
        """Run the technical harness suite and return quality gates + report."""
        request_id = ensure_request_id(req.request_id)
        try:
            from harness.orchestrator import run_technical_harness
        except ImportError as exc:
            return error_response(
                operation="technical_harness",
                request_id=request_id,
                error_type="InternalError",
                message=f"Harness module unavailable: {exc}",
                recoverable=True,
            )

        try:
            report = run_technical_harness(
                quick=req.quick,
                include_demo=req.include_demo,
                output_root=req.output_root,
            )
        except Exception as exc:
            return error_response(
                operation="technical_harness",
                request_id=request_id,
                error_type="InternalError",
                message=str(exc),
                recoverable=False,
            )

        from intentforge.contracts import (
            apply_response_contract,
            quality_gate_summary_from_report,
        )

        result: dict[str, Any] = {
            "ok": True,
            "operation": "technical_harness",
            "report": report,
        }
        return apply_response_contract(
            result,
            operation="technical_harness",
            request_id=request_id,
            quality_gate_report=report,
        )

    # ── Run metadata ──────────────────────────────────────────────

    @app.get("/v1/runs/recent", tags=["runs"], dependencies=[auth] if auth else [])
    async def list_recent_runs(
        kind: str = Query(default="parsed_runs", description="Run kind: parsed_runs or edit_parse_runs"),
        limit: int = Query(default=5, ge=1, le=100),
        output_root: str | None = Query(default=None),
        request_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """List recent parsed or edit-parse output runs."""
        request_id = ensure_request_id(request_id)
        return list_recent_runs_workflow(
            kind, limit, output_root, request_id=request_id
        )

    @app.get(
        "/v1/runs/{kind}/{run_id}",
        tags=["runs"],
        dependencies=[auth] if auth else [],
    )
    async def get_run_metadata(
        kind: str,
        run_id: str,
        output_root: str | None = Query(default=None),
        request_id: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Return run_metadata.json for a parsed or edit-parse output run."""
        request_id = ensure_request_id(request_id)
        return get_run_metadata_workflow(
            kind, run_id, output_root, request_id=request_id
        )

    # ── Artifact file serving ──────────────────────────────────────

    @app.get(
        "/v1/artifacts/{relative_path:path}",
        tags=["artifacts"],
        dependencies=[auth] if auth else [],
    )
    async def serve_artifact(relative_path: str):
        """Serve an artifact file from the output directory.

        Only files under ``output/`` are served.  Path traversal is
        rejected with 403.
        """
        try:
            return serve_artifact_file(relative_path)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Artifact not found: {relative_path}")
