# Project Status

Current development target: Phase 10 on `phase-10-l-bracket`

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
- Phase 10: L-bracket model family in progress

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
- Last recorded result for Phase 10.5: `194 passed`

CadQuery-dependent tests require the optional CAD dependency.

## Benchmark Status

Release benchmark:

- `python -m intentforge.cli benchmark`
- Last recorded result for Phase 10.5: `82 passed, 0 failed`, pass rate `1.0000`
- Family split: `wall_mounted_bracket` 54 passed, `l_bracket` 28 passed

Benchmark reports are written under `output/benchmark/`.

## Next Planned Phase

Finish Phase 10 hardening for the L-bracket family, then consider a third model family only after regression coverage stays green.
