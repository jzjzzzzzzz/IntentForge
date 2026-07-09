# Project Status

Current development target: Phase 16 product demo workflow and API client examples on `main`

Current supported model families:

- `wall_mounted_bracket` / mounting plate
- `l_bracket` / right angle bracket

## Completed Phases

- Phase 1: repository structure and schemas
- Phase 2: CadQuery generation for wall-mounted bracket
- Phase 3: geometry and intent validation
- Phase 4: structured edit intent handling
- Phase 4.5: output management and traceability
- Phase 5: deterministic natural-language prompt parsing
- Phase 5.5: optional feature intent support
- Phase 5.6: parsed output management and traceability
- Phase 6: deterministic natural-language edit parsing
- Phase 6.5: mounting-hole pattern intent support
- Phase 7: MCP wrapper
- Phase 8: benchmark and regression suite
- Phase 9: demo, documentation, and release readiness
- Phase 10: L-bracket model family
- Phase 10.5: L-bracket hardening and PR readiness
- Phase 10.6: developer experience, doctor command, and CI
- Phase 11.1: shape inspector and topology-informed validation foundation
- Phase 11.2: volume delta validation harness
- Phase 11.3: parametric sweep harness
- Phase 11.4: edit preservation harness
- Phase 11.5: adversarial rejection harness
- Phase 12: technical harness orchestrator and quality gates
- Phase 13: production tool interface and API contract hardening
- Phase 14: optional LLM intent translator with schema guardrails
- Phase 15: optional local HTTP API server / product backend
- Phase 16: product demo workflow and API client examples

## Current Capabilities

- parse simple wall-mounted bracket and mounting plate prompts
- parse simple L-bracket and right-angle bracket prompts
- generate named parameter tables
- preserve assumptions and unknowns
- plan active feature history
- build CadQuery models
- export STEP/STL files
- validate geometry and intent
- parse and apply simple natural-language edits
- reject unsupported prompts and edits clearly
- support no-hole, two-hole, and four-hole patterns
- support L-bracket no-hole and two-holes-per-leg patterns
- support optional L-bracket triangular gusset intent
- write traceable latest and persistent outputs
- expose workflows through optional MCP tools
- run a deterministic benchmark suite
- run topology inspection and volume delta harnesses
- run parametric sweep, edit preservation, and adversarial rejection harnesses
- run a unified technical harness with quality gates
- return standard tool/API response envelopes with request IDs
- return standard artifact references and structured error objects
- support dry-run parse-build and edit-apply workflows without STEP/STL export
- optionally translate prompts and edits with an LLM provider
- guard LLM output before deterministic CAD workflows run
- expose all workflows through an optional FastAPI HTTP API
- optional Bearer token auth via INTENTFORGE_API_TOKEN
- safe artifact file serving (only files under output/)
- path traversal rejection for artifact requests
- CLI serve subcommand (intentforge serve)
- product demo workflow examples (api_client_demo.py, product_workflow_demo.py)
- mocked demo script tests (no live server required)

## Current Limitations

- L-bracket support is limited to 0 or 2 holes per leg
- no four-hole L-bracket pattern yet
- no sheet-metal unfold pattern
- no curved or adjustable L-brackets
- inside fillet intent is represented and validated, but robust inside-corner fillet geometry is future work
- no GUI
- no required LLM calls in the deterministic core
- LLM support is optional and disabled unless a provider is configured
- LLM output cannot directly generate CadQuery code or CAD geometry
- no desktop CAD control
- no arbitrary CAD
- no topological feature detection from solids yet
- deterministic parser only
- no freeform hole placement
- HTTP API does not serve generated CAD files for download yet (artifact endpoint serves files under output/)

## Test Status

Release verification:

- `python -m pytest`
- Last recorded result for Phase 16: 354 passed, 1 skipped (includes 40 API + 12 demo script tests)

CadQuery-dependent tests require the optional CAD dependency.

API tests require the optional API dependency (fastapi + uvicorn + httpx).

## Benchmark Status

Release benchmark:

- `python -m intentforge.cli benchmark`
- Last recorded result for Phase 11.5: `97 passed, 0 failed`, pass rate `1.0000`
- Family split: `wall_mounted_bracket` 69 passed, `l_bracket` 28 passed

Benchmark reports are written under `output/benchmark/`.

## Harness Status

Technical harness command:

- `python -m intentforge.cli technical-harness --quick`
- `python -m intentforge.cli technical-harness --include-demo`

Default quality gates require benchmark, sweep, and edit preservation rates of at least `0.95`, adversarial rejection success of `1.0`, zero unsafe acceptances, and zero unexpected failures or exceptions.

## API Contract Status

Phase 13 standardizes external workflow and MCP responses with:

- `request_id`
- `operation`
- normalized artifact refs
- validation summaries
- quality gate summaries where relevant
- structured recoverable errors
- `dry_run` and `cad_exported` status

## LLM Translator Status

Phase 14 adds an optional provider interface, schema guardrails, mock provider, CLI commands, and MCP tools for LLM-based intent translation.

LLM commands:

- `python -m intentforge.cli llm-parse "..."`
- `python -m intentforge.cli llm-parse-build "..."`
- `python -m intentforge.cli llm-edit-parse l_bracket "..."`
- `python -m intentforge.cli llm-edit-apply l_bracket "..."`

If no provider is configured, these commands return `LLMProviderUnavailableError`. Tests use `MockLLMProvider` only and make no real API calls.

## HTTP API Status

Phase 15 adds an optional FastAPI HTTP API server with:

- GET /health — API health check
- POST /v1/parse — parse a deterministic CAD prompt
- POST /v1/parse-build — parse, build, export, validate
- POST /v1/edit-parse — parse a natural-language edit
- POST /v1/edit-apply — parse and apply an edit
- POST /v1/llm/parse — LLM-translate a prompt
- POST /v1/llm/parse-build — LLM-translate, guard, build, validate
- POST /v1/llm/edit-parse — LLM-translate an edit
- POST /v1/llm/edit-apply — LLM-translate, guard, apply edit
- POST /v1/technical-harness — run technical harness
- GET /v1/runs/recent — list recent runs
- GET /v1/runs/{kind}/{run_id} — get run metadata
- GET /v1/artifacts/{path} — serve artifact files (safe, no path traversal)

All endpoints return contract-compatible ToolResponse envelopes. Optional Bearer token auth via INTENTFORGE_API_TOKEN. API tests skip cleanly when fastapi is not installed.

Start server: `intentforge serve [--host HOST] [--port PORT] [--token TOKEN]`

Phase 16 adds product demo workflow scripts and documentation:
- examples/api_client_demo.py — 5-step API client (health, parse-build dry, parse-build full, edit-apply dry, edit-apply full)
- examples/product_workflow_demo.py — 7-step commercial workflow (parse → dry-run → build → edit → validate → rejection → artifact list)
- docs/product_demo.md — startup commands, example API calls, response snippets, dry_run, artifact refs, token auth
- tests/test_demo_scripts.py — 12 tests (import safety, missing httpx, mocked API steps, rejection)
- README.md updated with HTTP API and Product Demo sections

All demo scripts fail clearly if API server is not running. No live server in pytest. No release tag.

## Next Planned Phase

Phase 17: user workflow templates / agent integration examples.
