# IntentForge

[![Tests](https://github.com/jzjzzzzzzz/IntentForge/actions/workflows/tests.yml/badge.svg)](https://github.com/jzjzzzzzzz/IntentForge/actions/workflows/tests.yml)

IntentForge is a deterministic CAD intent pipeline for turning simple engineering language into editable, explainable, validated parametric CAD models.

It is not a general text-to-CAD generator. The goal is not to produce geometry that merely looks right once. The goal is to preserve the design intent behind the model so later edits can update named parameters and active features without losing the original assumptions, constraints, and feature history.

The current implementation is intentionally narrow:

```text
wall_mounted_bracket / mounting plate
l_bracket / right angle bracket
```

IntentForge currently uses Python, Pydantic schemas, CadQuery, pytest, deterministic regex parsing, optional MCP wrappers, and an optional LLM intent translator. The deterministic CAD core does not depend on an LLM.

## Pipeline

The current pipeline is:

```text
natural language
-> structured intent
-> named parameter table
-> constraint graph
-> feature plan
-> CadQuery model
-> STEP/STL exports
-> validation report
-> edit intent
-> regenerated CAD
```

Each stage writes structured artifacts so a reviewer or coding agent can inspect what the system inferred, which dimensions are named, which assumptions were made, which optional features are active, and why validation passed or failed.

## Why This Is Different

Normal text-to-CAD demos often generate a one-off model from a prompt. That can work for visual sketches, but it is brittle when the design changes.

IntentForge keeps the editable model state explicit:

- important dimensions are named parameters
- optional features are represented by feature flags
- assumptions and unknowns are recorded
- feature steps include reasons
- validation checks produce structured reports
- edits modify the existing intent and parameter table instead of treating every change as a new prompt

## Supported Scope

IntentForge currently supports two deterministic model families:

- `wall_mounted_bracket` / mounting plate
- `l_bracket` / right angle bracket

Supported features:

- L-bracket base leg and vertical leg parameters
- L-bracket no holes or two holes per leg
- optional L-bracket triangular gusset
- no mounting holes
- two horizontal symmetric mounting holes
- four rectangular/corner mounting holes
- optional center cutout
- optional rounded corners
- optional edge fillets
- deterministic natural-language edits
- structured edit JSON
- benchmark suite
- optional MCP wrapper
- optional LLM intent translator with schema guardrails

Unsupported by design in this phase:

- arbitrary CAD objects
- new model families
- four-hole L-bracket patterns
- freeform L-bracket hole placement
- curved or adjustable L-brackets
- sheet-metal unfold patterns
- robust geometric inside-corner filleting for L-brackets
- required LLM parsing in the deterministic core
- LLM-generated CAD code or direct LLM geometry generation
- GUI
- SolidWorks, Fusion, or FreeCAD desktop control
- freeform hole placement
- circular or diagonal hole patterns
- topological hole detection from exported solids

## Installation

Create an environment and install the released package:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install intentforge
```

Or install the source tree in editable mode for development:

```bash
python -m pip install -e .
```

CadQuery is optional for non-CAD parser tests, but required for real STEP/STL generation:

```bash
python -m pip install "intentforge[cad]"
```

Optional MCP support is installed separately:

```bash
python -m pip install "intentforge[mcp]"
```

Optional LLM translation can be configured from the interactive client. You do not need to edit files by hand:

```bash
intentforge interactive
# then follow the first-run setup prompt, or run:
intentforge config setup
```

IntentForge also accepts `OPENAI_API_KEY` and the `INTENTFORGE_LLM_*` environment variables for non-interactive use. Do not commit real keys.

For the interactive terminal client (Claude Code-like experience):

```bash
python -m pip install "intentforge[client]"
intentforge interactive
```

Run the test suite:

```bash
python -m pytest
```

Check the local development environment:

```bash
python -m intentforge.cli doctor
```

## Usage

Parse a prompt into structured intent artifacts:

```bash
python -m intentforge.cli parse "Make a wall-mounted bracket 120 mm wide and 60 mm tall with two screw holes."
```

Parse, build, export STEP/STL, and validate:

```bash
python -m intentforge.cli parse-build "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes."
```

Build an L-bracket:

```bash
python -m intentforge.cli parse-build "Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, and 6 mm thick."
```

Build an L-bracket with holes on both legs:

```bash
python -m intentforge.cli parse-build "Make an L-bracket with two holes on the base and two holes on the vertical face."
```

Build and validate the bundled bracket example:

```bash
python -m intentforge.cli build-example bracket
python -m intentforge.cli validate-example bracket
```

Parse a natural-language edit:

```bash
python -m intentforge.cli edit-parse "Make it 150 mm wide but keep the same thickness."
```

Parse and apply an edit to the bundled bracket example:

```bash
python -m intentforge.cli edit-parse-apply bracket "Change it to four mounting holes."
```

Parse and apply an edit to the bundled L-bracket example:

```bash
python -m intentforge.cli edit-parse-apply l_bracket "Make the base leg 120 mm long."
```

Rejected edits are reported without exporting new edited CAD:

```bash
python -m intentforge.cli edit-parse-apply bracket "Change it to three mounting holes."
```

Run parse-build without exporting STEP/STL files:

```bash
python -m intentforge.cli parse-build "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes." --dry-run
```

Run an edit without exporting edited STEP/STL files:

```bash
python -m intentforge.cli edit-parse-apply bracket "Make it 150 mm wide but keep the same thickness." --dry-run
```

Use the optional LLM translator with the deterministic mock provider:

```bash
python -m intentforge.cli llm-parse "Make a wall-mounted bracket 120 mm wide with two screw holes." --mock-provider
python -m intentforge.cli llm-parse-build "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes." --dry-run --mock-provider
python -m intentforge.cli llm-edit-parse l_bracket "Add a triangular gusset." --mock-provider
python -m intentforge.cli llm-edit-apply l_bracket "Add a triangular gusset." --dry-run --mock-provider
```

Without a configured provider, LLM commands return a structured `LLMProviderUnavailableError`.

Run the parametric sweep harness:

```bash
python -m intentforge.cli sweep --max-cases-per-family 30
```

Run the edit preservation harness:

```bash
python -m intentforge.cli edit-harness
```

Run the adversarial rejection harness:

```bash
python -m intentforge.cli adversarial-harness
```

Run the unified technical harness and quality gates:

```bash
python -m intentforge.cli technical-harness --quick
python -m intentforge.cli technical-harness --include-demo
```

## Demo

Run the release demo:

```bash
python -m intentforge.cli demo
```

The demo runs parse-build examples, accepted edits, an intentionally rejected vague edit, and the benchmark suite. It writes a traceable demo run under:

```text
output/demo_runs/<run_id>/
```

The run directory contains `demo_report.json`, `demo_summary.txt`, generated CAD outputs, validation reports, edit reports, and benchmark reports.

## Benchmark

Run the deterministic regression benchmark:

```bash
python -m intentforge.cli benchmark
```

The benchmark covers parsing, CAD generation, optional features, hole patterns, rejection behavior, natural-language edits, validation, output traceability, and family-level results for `wall_mounted_bracket` and `l_bracket`.

Reports are written to:

```text
output/benchmark/benchmark_report.json
output/benchmark/benchmark_summary.txt
output/benchmark/runs/<run_id>/
```

## API Contract

Workflow and MCP outputs use a standard response envelope with `ok`, `request_id`, `run_id`, `object_type`, `operation`, artifact references, validation summaries, quality gate summaries, warnings, metadata, and structured errors on failure.

Rejected prompts and edits are recoverable tool responses with `ok: false`, `cad_exported: false`, and no standard artifact refs. Compatibility keys such as `latest_outputs`, `persistent_outputs`, `validation_valid`, and `message` are still preserved.

See [docs/api_contract.md](docs/api_contract.md).

## LLM Translator

The LLM translator is optional. It may translate prompts or edits into structured IntentForge JSON, but it never writes CadQuery code and never directly generates CAD. Schema guardrails reject unsupported families, unsupported geometry, unsupported hole counts, arbitrary coordinates, and vague optimization requests before deterministic workflows can build or edit anything.

See [docs/llm_translator.md](docs/llm_translator.md).

## Edit Preservation Harness

The edit preservation harness stress-tests the core differentiator in IntentForge: changing an existing design without losing intent.

It runs multi-step edit chains for both supported families and checks:

- changed parameters are the ones the edit requested
- preserved parameters remain unchanged
- optional feature state stays consistent
- regenerated CAD still validates
- topology inspection and volume delta checks remain coherent when applicable
- rejected edits do not export CAD

Run it with:

```bash
python -m intentforge.cli edit-harness
```

Latest reports are written to:

```text
output/harness/edit_preservation_report.json
output/harness/edit_preservation_summary.txt
```

Persistent run artifacts are written to:

```text
output/harness/edit_preservation_runs/<run_id>/
```

## Adversarial Rejection Harness

The adversarial rejection harness verifies that unsupported objects, unsupported geometry, vague optimization requests, invalid dimensions, unsupported hole counts, and unsafe fallback prompts are rejected clearly.

It checks that rejected cases include an error message and do not export STEP/STL files.

Run it with:

```bash
python -m intentforge.cli adversarial-harness
```

Reports are written to:

```text
output/harness/adversarial_report.json
output/harness/adversarial_summary.txt
output/harness/adversarial_runs/<run_id>/
```

## Technical Harness

The technical harness orchestrator runs the benchmark, parametric sweep, edit preservation harness, adversarial rejection harness, volume delta checks, and shape inspection checks as one quality gate suite.

Run a faster local check:

```bash
python -m intentforge.cli technical-harness --quick
```

Run the full harness with the demo workflow included:

```bash
python -m intentforge.cli technical-harness --include-demo
```

Default quality gates require:

- benchmark pass rate >= 0.95
- sweep pass rate >= 0.95
- edit preservation rate >= 0.95
- adversarial rejection success rate == 1.0
- unsafe acceptances == 0
- unexpected failures and exceptions == 0

Reports are written to:

```text
output/harness/technical_harness_report.json
output/harness/technical_harness_summary.txt
output/harness/technical_harness_runs/<run_id>/
```

## HTTP API Server

IntentForge ships an optional local HTTP API server (Phase 15).  It is a thin FastAPI layer over the same deterministic workflows, returning contract-compatible `ToolResponse` envelopes on every endpoint.

Install API dependencies:

```bash
python -m pip install "intentforge[api]"
```

Start the server:

```bash
intentforge serve
# or:  python -m intentforge.api.server
# with auth:  intentforge serve --token my-secret-token
# custom host/port:  intentforge serve --host 0.0.0.0 --port 9000

# Environment variables for python -m entry point:
# INTENTFORGE_API_HOST  (default: 127.0.0.1)
# INTENTFORGE_API_PORT  (default: 8765)
# INTENTFORGE_API_TOKEN (optional Bearer auth token)
```

API docs are at `http://127.0.0.1:8765/docs`.

Key endpoints:

- `GET /health` — health check
- `POST /v1/parse` — deterministic prompt parsing
- `POST /v1/parse-build` — parse, build STEP/STL, validate (supports `dry_run`)
- `POST /v1/edit-apply` — parse and apply edit (supports `dry_run`)
- `POST /v1/llm/parse` / `/llm/parse-build` / `/llm/edit-parse` / `/llm/edit-apply` — optional LLM translation
- `GET /v1/runs/recent` / `/runs/{kind}/{run_id}` — run metadata
- `GET /v1/artifacts/{path}` — safe artifact file serving

See [docs/api_contract.md](docs/api_contract.md) and [docs/product_demo.md](docs/product_demo.md).

## Interactive Terminal Client

IntentForge ships an optional interactive terminal client (like Claude Code's experience) with rich colored output, spinners, session tracking, and auto-completion.

Install client dependencies:

```bash
python -m pip install "intentforge[client]"
```

Start the interactive session:

```bash
intentforge interactive
```

On first launch, IntentForge offers to configure optional LLM translation. The setup wizard uses up/down arrow selection in an interactive terminal, and falls back to typed choices in scripts. It supports OpenAI, OpenAI-compatible endpoints, the deterministic mock provider, or skipping LLM setup entirely. Saved settings are written to `~/.intentforge/config.json` with owner-only permissions where supported, and API keys are masked when displayed.

Available commands inside the session:

| Command | Description |
|---------|-------------|
| `parse "prompt"` | Parse a natural-language prompt into structured intent |
| `parse-build [--dry-run] "prompt"` | Parse + generate CAD + export STEP/STL |
| `edit <target> "edit request"` | Edit an existing model with intent preservation |
| `llm-parse "prompt"` | LLM-translate prompt (requires LLM config) |
| `llm-parse-build "prompt"` | LLM-translate + build |
| `demo` | Run the full product demo |
| `doctor` | Check environment health |
| `status` | Show current session context |
| `config` | Show masked LLM configuration |
| `config setup` | Configure OpenAI, compatible, or mock LLM provider |
| `history` | Show command history |
| `quit` | Exit session |

The client works without `rich` and `prompt_toolkit` — it gracefully falls back to plain text output and basic `input()` prompts.

## Product Demo Workflow

Two demo scripts show how a real user or external agent would call IntentForge end-to-end via the HTTP API:

```bash
# Start the server first:
intentforge serve

# Minimal 5-step API client demo:
python examples/api_client_demo.py

# Full 7-step product workflow demo (parse → dry-run → build → edit → validate → rejection → artifact list):
python examples/product_workflow_demo.py
```

Both scripts fail clearly if the API server is not running.  With auth:

```bash
python examples/api_client_demo.py --token my-secret-token
```

See [docs/product_demo.md](docs/product_demo.md) for the full walkthrough.

Phase 12 adds this harness command only; it does not create a new release tag.

## MCP Usage

IntentForge can be exposed as an optional MCP tool server for coding agents:

```bash
python -m mcp_server.server
```

The MCP server is a thin wrapper around existing workflows. It does not duplicate parser, generator, validator, or editor logic. Optional LLM MCP tools only translate structured intent and still pass through schema guardrails.

Available tool functions include:

- `parse_cad_prompt`
- `parse_build_cad_prompt`
- `parse_edit_prompt`
- `parse_apply_edit_prompt`
- `build_example_bracket`
- `validate_example_bracket`
- `list_recent_runs`
- `get_run_metadata`

## License

License: Apache-2.0. See `LICENSE`.

## Project Structure

```text
benchmark/      Deterministic benchmark corpus and runner
demo/           Release demo script and notes
docs/           Architecture, design intent, validation, benchmark, LLM, MCP, and roadmap docs
examples/       Bundled wall-bracket and L-bracket prompt, intent, parameters, constraints, feature plan, and edit examples
harness/        Topology, volume delta, sweep, edit-preservation, adversarial, and orchestrator harnesses
intentforge/    Core schemas, parser, planner, generator, validator, editor, workflows, and CLI
mcp_server/     Optional MCP wrapper around core workflows
output/         Generated artifacts
tests/          Pytest coverage
```

## Roadmap

Near-term roadmap:

- Phase 10: harden the new L-bracket family while preserving the same intent-first architecture
- add an electronics enclosure family
- add topological feature detection for generated solids
- add an LLM-assisted parser that emits the same structured schemas
- consider GUI or CAD-plugin integration after the core pipeline is more mature

See `docs/roadmap.md` for more detail.
