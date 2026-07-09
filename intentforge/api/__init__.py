"""Optional FastAPI HTTP API layer for IntentForge.

This module is only usable when the ``api`` optional extra is installed:
    python -m pip install -e '.[api]'

All endpoints return contract-compatible ToolResponse envelopes.
"""

from intentforge.api.app import create_app
from intentforge.api.server import serve

__all__ = ["create_app", "serve"]
