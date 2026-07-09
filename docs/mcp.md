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
- optional LLM intent translation
- optional LLM translate-build and translate-apply workflows

## Design

The MCP layer is intentionally thin. It calls shared IntentForge workflows and returns structured results. It does not duplicate parser, generator, validator, editor, or LLM translator logic.

MCP responses include family data through workflow results such as `object_type`, parsed intent metadata, and run metadata where applicable.

## Response Contract

MCP tool outputs follow the same standard response envelope as the shared workflows:

- `ok`
- `request_id`
- `run_id` when a traceable run is created
- `object_type` where relevant
- `operation`
- `artifacts`
- `validation`
- `quality_gates` where relevant
- `warnings`
- `metadata`
- structured `error` on failure

Rejected prompts and edits return `ok: false` and a recoverable error object. Rejected edits also report `cad_exported: false`.

`parse_build_cad_prompt` and `parse_apply_edit_prompt` accept `dry_run` so callers can validate feasibility without exporting STEP/STL artifacts.

See `docs/api_contract.md` for the shared contract details.

## Optional LLM Tools

Additional MCP tool functions are available:

- `llm_parse_cad_prompt`
- `llm_parse_build_cad_prompt`
- `llm_parse_edit_prompt`
- `llm_parse_apply_edit_prompt`

These tools load an optional provider from environment variables. If no provider is configured, they return `ok=false` with `LLMProviderUnavailableError`.

The LLM tools only translate intent or edit JSON. They do not generate CadQuery code or bypass deterministic validation and schema guardrails.
