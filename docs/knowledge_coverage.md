# Engineering Knowledge Coverage

IntentForge uses a deterministic capability coverage layer to describe what the project actually supports, partially supports, and rejects by design.

Per-design assurance cases use these declarations to identify exercised capabilities and relevant boundaries; they do not alter capability status based on one successful run.

Coverage is not a marketing support percentage. A capability can be:

- `supported`: implemented and verified for the declared model family and stages.
- `partially_supported`: implemented with explicit limitations.
- `unsupported`: outside scope and expected to be rejected safely.
- `not_applicable`: not relevant for the declared family or stage.

Unsupported boundaries are valuable. They document where IntentForge should reject a request instead of silently producing incorrect CAD.

## Manifest

The packaged manifest is:

```text
src/intentforge/knowledge/data/capability_manifest.yaml
```

It declares:

- capability ID and title
- CAD family
- support status
- applicable pipeline stages
- contributing rule IDs and knowledge packs
- implementation evidence
- verification evidence
- limitations
- rejection behavior
- provenance and version

The manifest does not duplicate engineering formulas or CAD generation logic. Engineering rules remain authoritative in:

```text
src/intentforge/knowledge/packs/data/*.yaml
```

## Evidence

Evidence references are identifiers, not executable code. Supported evidence types include:

- `rule`
- `parser`
- `schema`
- `generator`
- `validator`
- `topology_metric`
- `feature_recognizer`
- `reasoning_case`
- `golden_case`
- `benchmark_case`
- `test`
- `rejection_case`
- `documentation`

The resolver validates references against deterministic registries such as rule IDs, rule pack IDs, benchmark case IDs, golden reasoning case IDs, and known implementation identifiers. It does not import arbitrary modules from YAML, run callables, or read arbitrary filesystem paths.

Phase 22 adds a separate evidence manifest and trust layer. The capability manifest may still hold lightweight evidence references for compatibility, while `evidence_manifest.yaml` defines richer evidence records with roles, verification methods, freshness policies, and limitation metadata.

See also:

- [Engineering Evidence Traceability](evidence_traceability.md)
- [Capability Evidence Bundles](evidence_bundles.md)
- [Engineering Evidence Trust Report](trust_report.md)

## Coverage Checks

Coverage validation checks:

- duplicate capability IDs
- unknown families, statuses, stages, rule IDs, pack IDs, and evidence references
- supported capabilities missing implementation or verification evidence
- partial capabilities missing limitations
- unsupported capabilities missing rejection evidence
- active engineering rules not mapped to any declared capability
- duplicate evidence entries
- deterministic report IDs

All 10 active engineering rules are expected to map to at least one capability unless explicitly marked cross-cutting with a reason.

## Commands

```bash
python -m intentforge.cli knowledge coverage
python -m intentforge.cli knowledge coverage --json
python -m intentforge.cli knowledge coverage-validate
python -m intentforge.cli knowledge capability-validate
```

The JSON output is stable and intended for future API, MCP, and QA tooling.

## Limitations

The coverage layer describes current project behavior. It does not add CAD support. It does not certify engineering safety, run FEA, or imply support for arbitrary CAD. Current declared families remain:

- `wall_mounted_bracket`
- `l_bracket`
