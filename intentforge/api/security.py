"""Optional Bearer-token authentication for IntentForge HTTP API.

If the environment variable ``INTENTFORGE_API_TOKEN`` is set, all API
endpoints require ``Authorization: Bearer <token>``.  If unset, auth is
disabled and all endpoints are open.
"""

import os
from typing import Any


class OptionalTokenAuth:
    """Lightweight optional Bearer token guard for FastAPI dependency injection."""

    def __init__(self) -> None:
        self._enabled: bool = False
        self._token: str | None = None

    def enable(self, token: str) -> None:
        """Enable auth with the given bearer token."""
        self._enabled = True
        self._token = token

    def is_enabled(self) -> bool:
        """Return whether auth is active."""
        return self._enabled

    async def __call__(self, authorization: str | None = None) -> dict[str, Any]:
        """FastAPI Depends-compatible callable.

        The ``authorization`` parameter must be annotated with Header()
        when used as a dependency — see auth_dependency().
        Returns an empty dict on success; raises 401 on failure.
        """
        if not self._enabled:
            return {}

        from fastapi import HTTPException

        if not authorization:
            raise HTTPException(
                status_code=401,
                detail="Missing Authorization header. Expected: Bearer <token>",
            )

        parts = authorization.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise HTTPException(
                status_code=401,
                detail="Invalid Authorization header format. Expected: Bearer <token>",
            )

        if parts[1] != self._token:
            raise HTTPException(
                status_code=401,
                detail="Invalid API token.",
            )

        return {"auth": "ok"}


optional_token_auth = OptionalTokenAuth()


def auth_dependency() -> Any:
    """Return a FastAPI Depends object (or None) based on auth state.

    When auth is enabled, returns Depends that injects the Authorization
    header into the callable.  When disabled, returns None so the
    dependencies list is empty.
    """

    if not optional_token_auth.is_enabled():
        return None

    from fastapi import Depends, Header

    async def _check_auth(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        return await optional_token_auth.__call__(authorization)

    return Depends(_check_auth)
