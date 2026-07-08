# MCP

IntentForge includes an optional MCP wrapper so coding agents can call the deterministic CAD intent pipeline through tools.

## Installation

```bash
python -m pip install -e ".[mcp]"
```

Core IntentForge functionality does not require MCP. MCP tests that require the protocol package may be skipped when the optional dependency is unavailable.

## Starting The Server

```bash
python -m mcp_server.server
```

## Tools

The wrapper exposes tools for:

- parsing a CAD prompt
- parsing, building, exporting, and validating a CAD prompt
- validating bundled wall-bracket or L-bracket examples
- parsing a natural-language edit
- parsing and applying a natural-language edit
- building bundled wall-bracket or L-bracket examples
- listing recent parsed or edit runs
- retrieving run metadata

## Design

The MCP layer is intentionally thin. It calls `intentforge.workflows` and returns structured results. It does not duplicate parser, generator, validator, or editor logic, and it does not call an LLM.

MCP responses include family data through workflow results such as `object_type`, parsed intent metadata, and run metadata where applicable.
