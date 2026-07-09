"""CLI ``serve`` subcommand for the IntentForge HTTP API server.

Run via:  intentforge serve [--host HOST] [--port PORT] [--token TOKEN]
"""

from __future__ import annotations

import os
import sys


def serve(host: str = "127.0.0.1", port: int = 8000, token: str | None = None) -> int:
    """Start the IntentForge HTTP API server.

    Parameters:
        host: Bind address (default 127.0.0.1).
        port: Bind port (default 8000).
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

    # Set token: CLI flag > env var > no auth.
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
