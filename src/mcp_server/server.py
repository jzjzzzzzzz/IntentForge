"""IntentForge MCP server entry point."""

from __future__ import annotations

from typing import Any

from mcp_server import tools


def create_server() -> Any:
    """Create and register the IntentForge FastMCP server."""

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "The optional MCP package is required to run the IntentForge MCP server. "
            "Install it with: python -m pip install -e '.[mcp]'"
        ) from exc

    server = FastMCP("IntentForge")
    for tool_func in tools.TOOLS.values():
        server.tool()(tool_func)
    return server


def main() -> int:
    """Run the IntentForge MCP server over the default MCP transport."""

    server = create_server()
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
