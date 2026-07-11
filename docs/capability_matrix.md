# Capability Matrix

The capability matrix defines product scope. Phase 24 policies consume capability references already embedded in assurance cases and cannot override a partially supported or unsupported capability status.

The capability matrix is a deterministic, filterable view of IntentForge's declared engineering capabilities.

Assurance records reference stable capability IDs from this matrix and combine them with run-level observations. A matrix row alone is not proof that a particular run passed.

Each row includes:

- capability ID
- CAD family
- support status
- applicable pipeline stages
- contributing knowledge packs
- contributing rule IDs
- implementation evidence count
- verification evidence count
- limitations
- rejection behavior
- provenance
- version

## Filtering

Use the CLI to inspect the matrix:

```bash
python -m intentforge.cli knowledge capability-matrix
python -m intentforge.cli knowledge capability-matrix --json
python -m intentforge.cli knowledge capability-matrix --family wall_mounted_bracket
python -m intentforge.cli knowledge capability-matrix --family l_bracket
python -m intentforge.cli knowledge capability-matrix --status supported
python -m intentforge.cli knowledge capability-matrix --stage engineering_reasoning
python -m intentforge.cli knowledge capability-matrix --knowledge-pack bracket_mechanical
python -m intentforge.cli knowledge capability-matrix --rule-id hole_edge_margin_001
```

## Current Scope

The matrix covers only the supported IntentForge model families:

- `wall_mounted_bracket`
- `l_bracket`

It includes supported capabilities, partial capabilities, and explicit unsupported boundaries. Unsupported entries are not counted as implemented CAD support; they document safe rejection behavior and verification evidence.

## Reproducibility

Matrix IDs are deterministic content hashes. The same capability manifest, rule packs, and filters produce the same matrix ID.

Capability version, rule version, pack version, and reasoning engine version are separate concepts. This separation keeps product claims, engineering rules, and reasoning behavior traceable independently.

Phase 22 adds evidence bundles on top of matrix rows. The matrix answers what is claimed; evidence bundles answer what specific evidence supports each claim and whether that evidence resolves.
