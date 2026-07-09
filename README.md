# IntentForge

[![Tests](https://github.com/jzjzzzzzzz/IntentForge/actions/workflows/tests.yml/badge.svg)](https://github.com/jzjzzzzzzz/IntentForge/actions/workflows/tests.yml)

IntentForge is a deterministic CAD intent pipeline for turning simple engineering language into editable, explainable, validated parametric CAD models.

It is not a general text-to-CAD generator. The goal is not to produce geometry that merely looks right once. The goal is to preserve the design intent behind the model so later edits can update named parameters and active features without losing the original assumptions, constraints, and feature history.

The current implementation is intentionally narrow:

```text
wall_mounted_bracket / mounting plate
l_bracket / right angle bracket
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

Unsupported by design in this phase:

- arbitrary CAD objects
- new model families
- four-hole L-bracket patterns
- freeform L-bracket hole placement
- curved or adjustable L-brackets
- sheet-metal unfold patterns
- robust geometric inside-corner filleting for L-brackets
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

Phase 12 adds this harness command only; it does not create a new release tag.

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

## License

License: Apache-2.0. See `LICENSE`.

## Project Structure

```text
benchmark/      Deterministic benchmark corpus and runner
demo/           Release demo script and notes
docs/           Architecture, design intent, validation, benchmark, MCP, and roadmap docs
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
