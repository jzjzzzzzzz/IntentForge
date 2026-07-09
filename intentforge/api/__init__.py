"""Optional FastAPI HTTP API layer for IntentForge.

This module is only usable when the ``api`` optional extra is installed:
    python -m pip install -e '.[api]'

All endpoints return contract-compatible ToolResponse envelopes.
"""

__all__ = ["create_app", "serve"]


def __getattr__(name: str):
    """Lazy import to avoid eager-loading server.py when running as ``-m`` entry point.

    When ``python -m intentforge.api.server`` is executed, Python first imports
    the parent package ``intentforge.api``.  If ``__init__.py`` eagerly imports
    ``intentforge.api.server``, the module lands in ``sys.modules`` before
    ``runpy`` can set ``__name__ == "__main__"`` — causing a RuntimeWarning
    and preventing the ``if __name__ == "__main__"`` block from ever executing.

    Lazy ``__getattr__`` ensures the parent package can be imported without
    triggering the server module, so ``python -m intentforge.api.server``
    works correctly.
    """

    if name == "create_app":
        from intentforge.api.app import create_app
        return create_app

    if name == "serve":
        from intentforge.api.server import serve
        return serve

    raise AttributeError(f"module 'intentforge.api' has no attribute {name}")
