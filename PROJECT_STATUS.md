# Project Status

Current release target: `v0.9.0`

Current supported model family: `wall_mounted_bracket` / mounting plate

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

## Current Capabilities

- parse simple wall-mounted bracket and mounting plate prompts
- generate named parameter tables
- preserve assumptions and unknowns
- plan active feature history
- build CadQuery models
- export STEP/STL files
- validate geometry and intent
- parse and apply simple natural-language edits
- reject unsupported prompts and edits clearly
- support no-hole, two-hole, and four-hole patterns
- write traceable latest and persistent outputs
- expose workflows through optional MCP tools
- run a deterministic benchmark suite

## Current Limitations

- one model family only: `wall_mounted_bracket`
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
- Last recorded result for this release target: `173 passed`

CadQuery-dependent tests require the optional CAD dependency.

## Benchmark Status

Release benchmark:

- `python -m intentforge.cli benchmark`
- Last recorded result for this release target: `54 passed, 0 failed`, pass rate `1.0000`

Benchmark reports are written under `output/benchmark/`.

## Next Planned Phase

Phase 10 should add a second small model family while preserving the same intent-first workflow and validation discipline.
