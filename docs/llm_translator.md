# LLM Intent Translator

Phase 14 adds an optional LLM-powered translation layer. The deterministic IntentForge CAD core remains unchanged.

The LLM is allowed to translate user language into structured IntentForge intent or edit JSON. It is not allowed to:

- generate CadQuery code
- generate CAD geometry
- write STEP/STL files
- bypass schema validation
- claim validation or generation happened
- invent unsupported model families or features

## Supported Families

The schema guard only accepts:

- `wall_mounted_bracket`
- `l_bracket`

Unsupported objects such as gears, enclosures, drone frames, hinges, shaft couplers, and arbitrary freeform CAD are rejected.

Unsupported geometry such as curved L-brackets, sheet-metal flat patterns, arbitrary hole coordinates, unsupported hole counts, and vague optimization requests are also rejected.

## Architecture

The LLM layer lives under `src/intentforge/llm/` in the source tree:

- `provider.py`: provider interface and optional provider loading
- `translator.py`: high-level translation workflows
- `prompts.py`: prompt templates
- `schema_guard.py`: guardrails and normalization
- `mock_provider.py`: deterministic provider for tests

Flow:

```text
prompt/edit text
-> LLM JSON translation
-> schema guard
-> normalized supported prompt/edit
-> deterministic IntentForge parser/editor
-> generator/validator if requested
```

## Provider Configuration

Core IntentForge does not require an LLM provider.

Interactive setup:

```bash
intentforge interactive
intentforge config setup
```

The setup wizard stores optional LLM settings in `~/.intentforge/config.json` with owner-only permissions where supported. In an interactive terminal, provider selection uses up/down arrows and Enter; in scripts, the wizard falls back to typed choices. Users can choose OpenAI, an OpenAI-compatible endpoint, the deterministic mock provider, or skip LLM setup. API keys are masked when displayed by `config`.

Environment variables are also supported for non-interactive deployments and take precedence over the saved config:

```bash
INTENTFORGE_LLM_PROVIDER=
INTENTFORGE_LLM_BASE_URL=
INTENTFORGE_LLM_MODEL=
INTENTFORGE_LLM_API_KEY=
```

For OpenAI specifically, IntentForge also accepts the standard `OPENAI_API_KEY` environment variable and defaults to the OpenAI API base URL when no custom base URL is provided.

Supported provider values:

- `mock`: deterministic mock provider
- `openai-compatible`: optional OpenAI-compatible chat completions endpoint
- `openai`: alias for OpenAI-compatible behavior

No API keys are committed. `.env` is ignored.

## CLI

LLM parse:

```bash
python -m intentforge.cli llm-parse "Make a wall-mounted bracket 120 mm wide with two screw holes."
```

LLM parse-build:

```bash
python -m intentforge.cli llm-parse-build "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes."
```

Dry run:

```bash
python -m intentforge.cli llm-parse-build "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes." --dry-run
```

LLM edit parse:

```bash
python -m intentforge.cli llm-edit-parse l_bracket "Add a triangular gusset."
```

LLM edit apply:

```bash
python -m intentforge.cli llm-edit-apply l_bracket "Add a triangular gusset."
```

For deterministic local testing:

```bash
python -m intentforge.cli llm-parse "Make a wall-mounted bracket 120 mm wide with two screw holes." --mock-provider
```

If no provider is configured, LLM commands return `ok=false` with `LLMProviderUnavailableError`.

## Response Contract

LLM workflows return the same Phase 13 tool response envelope:

- `ok`
- `request_id`
- `operation`
- `object_type`
- `artifacts`
- `validation`
- `warnings`
- `metadata`
- structured `error` on failure

## Example Success

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "operation": "llm_parse",
  "object_type": "wall_mounted_bracket",
  "normalized_prompt": "Make a wall-mounted bracket, 120 mm wide, with two screw holes.",
  "warnings": []
}
```

## Example Rejection

```json
{
  "ok": false,
  "request_id": "req_abc123",
  "operation": "llm_parse",
  "error": {
    "error_type": "UnsupportedObjectError",
    "message": "Unsupported object type: gear.",
    "recoverable": true
  },
  "cad_exported": false,
  "artifacts": []
}
```

## Testing

Tests use `MockLLMProvider` only. They do not make real API calls.

The deterministic parser, benchmark, technical harness, and demo remain available and unchanged.
