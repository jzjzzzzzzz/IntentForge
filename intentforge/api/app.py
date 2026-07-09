"""FastAPI application factory for IntentForge HTTP API."""

from __future__ import annotations

import os

from intentforge import __version__
from intentforge.api.security import optional_token_auth
from intentforge.api.routes import register_routes


def create_app() -> "fastapi.FastAPI":
    """Create and configure the IntentForge FastAPI application.

    Requires the ``api`` optional extra (fastapi + uvicorn).
    """

    try:
        import fastapi  # noqa: F401 — verify importable
    except ImportError as exc:
        raise RuntimeError(
            "The optional FastAPI dependency is required to run the IntentForge HTTP API. "
            "Install it with: python -m pip install -e '.[api]'"
        ) from exc

    from fastapi import FastAPI

    title = "IntentForge API"
    version = __version__
    description = (
        "Intent-preserving deterministic CAD pipeline — "
        "HTTP API for parse, build, edit, LLM translation, and harness endpoints."
    )
    app = FastAPI(
        title=title,
        version=version,
        description=description,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Optional Bearer token auth via INTENTFORGE_API_TOKEN env var.
    token = os.environ.get("INTENTFORGE_API_TOKEN")
    if token:
        optional_token_auth.enable(token)

    register_routes(app)
    return app
