# IntentForge

IntentForge is a deterministic CAD intent pipeline for turning simple engineering language into editable, explainable, validated parametric CAD models.

It is not a general text-to-CAD generator. The goal is not to produce geometry that merely looks right once. The goal is to preserve the design intent behind the model so later edits can update named parameters and active features without losing the original assumptions, constraints, and feature history.

The current implementation is intentionally narrow:

```text
wall_mounted_bracket / mounting plate only
```

IntentForge currently uses Python, Pydantic schemas, CadQuery, pytest, deterministic regex parsing, and optional MCP wrappers. It does not call an LLM.

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

IntentForge currently supports only `wall_mounted_bracket` and mounting-plate style prompts.

Supported features:

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

Unsupported by design in this phase:

- arbitrary CAD objects
- new model families
- LLM parsing
- GUI
- SolidWorks, Fusion, or FreeCAD desktop control
- freeform hole placement
- circular or diagonal hole patterns
- topological hole detection from exported solids

## Installation

Create an environment and install the development dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

CadQuery is optional for non-CAD parser tests, but required for real STEP/STL generation:

```bash
python -m pip install -e ".[cad]"
```

Optional MCP support is installed separately:

```bash
python -m pip install -e ".[mcp]"
```

Run the test suite:

```bash
python -m pytest
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

Rejected edits are reported without exporting new edited CAD:

```bash
python -m intentforge.cli edit-parse-apply bracket "Change it to three mounting holes."
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

The benchmark covers parsing, CAD generation, optional features, hole patterns, rejection behavior, natural-language edits, validation, and output traceability.

Reports are written to:

```text
output/benchmark/benchmark_report.json
output/benchmark/benchmark_summary.txt
output/benchmark/runs/<run_id>/
```

## MCP Usage

IntentForge can be exposed as an optional MCP tool server for coding agents:

```bash
python -m mcp_server.server
```

The MCP server is a thin wrapper around existing deterministic workflows. It does not duplicate parser, generator, validator, or editor logic, and it does not call an LLM.

Available tool functions include:

- `parse_cad_prompt`
- `parse_build_cad_prompt`
- `parse_edit_prompt`
- `parse_apply_edit_prompt`
- `build_example_bracket`
- `validate_example_bracket`
- `list_recent_runs`
- `get_run_metadata`

## Project Structure

```text
benchmark/      Deterministic benchmark corpus and runner
demo/           Release demo script and notes
docs/           Architecture, design intent, validation, benchmark, MCP, and roadmap docs
examples/       Bundled bracket prompt, intent, parameters, constraints, feature plan, and edit examples
intentforge/    Core schemas, parser, planner, generator, validator, editor, workflows, and CLI
mcp_server/     Optional MCP wrapper around core workflows
output/         Generated artifacts
tests/          Pytest coverage
```

## Roadmap

Near-term roadmap:

- Phase 10: add a second model family while preserving the same intent-first architecture
- add an L-bracket family
- add an electronics enclosure family
- add topological feature detection for generated solids
- add an LLM-assisted parser that emits the same structured schemas
- consider GUI or CAD-plugin integration after the core pipeline is more mature

See `docs/roadmap.md` for more detail.

