"""CLI ``serve`` subcommand and ``python -m`` entry point for the IntentForge HTTP API server.

Usage:

    # Via CLI subcommand:
    intentforge serve [--host HOST] [--port PORT] [--token TOKEN]

    # Via python -m (reads env vars for defaults):
    python -m intentforge.api.server

Environment variables for ``python -m`` entry point:

    INTENTFORGE_API_HOST   Bind address (default: 127.0.0.1)
    INTENTFORGE_API_PORT   Bind port    (default: 8765)
    INTENTFORGE_API_TOKEN  Bearer token for auth (optional)
"""

from __future__ import annotations

import os
import sys


def serve(host: str = "127.0.0.1", port: int = 8765, token: str | None = None) -> int:
    """Start the IntentForge HTTP API server.

    Parameters:
        host: Bind address (default 127.0.0.1).
        port: Bind port (default 8765).
        token: API bearer token.  If not set, reads INTENTFORGE_API_TOKEN
               env var.  If neither is set, auth is disabled.
    """

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print(
            "Error: uvicorn is required to run the IntentForge HTTP API server.\n"
            "Install it with: python -m pip install -e '.[api]'",
            file=sys.stderr,
        )
        return 1

    # Set token: argument > env var > no auth.
    effective_token = token or os.environ.get("INTENTFORGE_API_TOKEN")
    if effective_token:
        os.environ["INTENTFORGE_API_TOKEN"] = effective_token
        print("API auth enabled (token set).")
    else:
        print("API auth disabled (no token configured).")

    from intentforge.api.app import create_app

    app = create_app()

    print(f"IntentForge API server starting on http://{host}:{port}")
    print(f"API docs: http://{host}:{port}/docs")

    uvicorn.run(app, host=host, port=port)
    return 0


def main() -> int:
    """Entry point for ``python -m intentforge.api.server``.

    Reads configuration from environment variables:
        INTENTFORGE_API_HOST  → host (default 127.0.0.1)
        INTENTFORGE_API_PORT  → port (default 8765)
        INTENTFORGE_API_TOKEN → auth token (optional)
    """
    host = os.environ.get("INTENTFORGE_API_HOST", "127.0.0.1")
    port = int(os.environ.get("INTENTFORGE_API_PORT", "8765"))
    token = os.environ.get("INTENTFORGE_API_TOKEN")  # may be None
    return serve(host=host, port=port, token=token)


if __name__ == "__main__":
    raise SystemExit(main())
