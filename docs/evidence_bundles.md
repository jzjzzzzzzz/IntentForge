# Capability Evidence Bundles

Phase 22 assembles one evidence bundle per declared capability.

A bundle connects a capability claim to the evidence definitions and observations that support it. This makes it possible to inspect what supports a supported capability, what documents a partial limitation, and what verifies an unsupported boundary rejection.

## Bundle Contents

Each bundle includes:

- capability ID
- CAD family
- capability status
- implementation evidence
- verification evidence
- boundary evidence
- limitation evidence
- provenance evidence
- packaging evidence
- required evidence IDs
- resolved evidence IDs
- unresolved evidence IDs
- failed evidence IDs
- stale evidence IDs
- evidence completeness
- deterministic bundle ID

Bundle statuses are precise:

- `evidence_complete`
- `evidence_partial`
- `evidence_failed`
- `evidence_unresolved`
- `boundary_verified`
- `not_applicable`

## Unsupported Boundaries

Unsupported capabilities are not counted as implemented. They are evaluated by boundary evidence, usually deterministic rejection benchmark cases.

Examples include:

- freeform hole placement
- unsupported L-bracket four-hole patterns
- curved, adjustable, or sheet-metal L-bracket requests
- arbitrary non-bracket CAD requests

## Partial Capabilities

Partially supported capabilities must include limitation evidence. For example, feature recognition is topology-informed and useful for generated supported models, but it is not full industrial CAD feature recognition from arbitrary solids.

## Commands

```bash
python -m intentforge.cli knowledge evidence-bundles
python -m intentforge.cli knowledge evidence-bundles --json
python -m intentforge.cli knowledge evidence-bundles --family wall_mounted_bracket
python -m intentforge.cli knowledge evidence-bundles --family l_bracket
python -m intentforge.cli knowledge evidence-bundles --capability l_triangular_gusset
```

## Determinism

Bundle IDs are deterministic content hashes derived from the capability ID, required evidence IDs, resolved evidence IDs, unresolved evidence IDs, failed evidence IDs, stale evidence IDs, and bundle status. Runtime timestamps are not included in deterministic IDs.
