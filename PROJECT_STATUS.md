# Project Status

Current development target: Phase 12 technical harness orchestrator on `main`

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

## Current Limitations

- L-bracket support is limited to 0 or 2 holes per leg
- no four-hole L-bracket pattern yet
- no sheet-metal unfold pattern
- no curved or adjustable L-brackets
- inside fillet intent is represented and validated, but robust inside-corner fillet geometry is future work
- no GUI
- no LLM calls
- no desktop CAD control
- no arbitrary CAD
- no topological feature detection from solids yet
- deterministic parser only
- no freeform hole placement

## Test Status

Release verification:

- `python -m pytest`
- Last recorded result for Phase 11.5: `267 passed, 1 skipped`

CadQuery-dependent tests require the optional CAD dependency.

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

Phase 12 adds the orchestrator command only. It does not create a new release tag.

## Next Planned Phase

Complete Phase 12 verification, then consider future topology-aware validation improvements only after the unified harness stays green.
