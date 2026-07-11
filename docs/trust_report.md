# Engineering Evidence Trust Report

Phase 22 adds a deterministic trust report for declared IntentForge capability evidence.

Project-level trust reports describe evidence for declared framework capabilities. Phase 23 assurance cases separately record whether a capability was exercised and observed in one design run. A complete project evidence bundle does not automatically prove a run-level geometry claim.

The trust report is not a vague AI trust score. It is a structured evidence-quality report for the declared scope.

## What It Reports

The report includes:

- declared capability count
- supported capability count
- partially supported capability count
- unsupported boundary count
- total evidence definition count
- required evidence count
- verified evidence count
- failed evidence count
- unresolved evidence count
- unavailable evidence count
- stale evidence count
- orphan evidence count
- duplicate evidence ID count
- duplicate normalized reference count
- family mismatch count
- stage mismatch count
- unknown capability, rule, and pack references
- implementation evidence completeness
- verification evidence completeness
- boundary evidence completeness
- limitation evidence completeness
- per-family summaries
- per-stage summaries
- per-evidence-type summaries
- per-evidence-role summaries
- deterministic report ID
- overall trust gate result

Completeness metrics include numerators and denominators. For example:

```text
verification evidence completeness =
verified required verification evidence / total required verification evidence
```

Unsupported capabilities do not reduce implementation evidence completeness merely because they are intentionally unsupported. Their boundary evidence is measured separately.

## Quality Gates

The technical harness includes a lightweight evidence trust section. It checks:

- evidence manifest validation
- duplicate evidence IDs
- unknown capability, rule, and pack references
- unsafe file references
- family and stage mismatches
- supported capabilities missing implementation or verification evidence
- partial capabilities missing limitation evidence
- unsupported boundaries missing rejection evidence
- orphan evidence definitions
- deterministic bundle IDs
- deterministic trust report IDs

## Commands

```bash
python -m intentforge.cli knowledge trust-report
python -m intentforge.cli knowledge trust-report --json
python -m intentforge.cli knowledge trust-report --verify
python -m intentforge.cli knowledge trust-validate
python -m intentforge.cli technical-harness --quick
```

`trust-report --verify` runs safe internal runtime verification where available and still distinguishes static resolution from runtime verification.

## Limitations

The trust report means evidence is complete for the declared IntentForge scope. It does not mean:

- universal engineering correctness
- load-specific certification
- FEA-backed safety proof
- support for arbitrary CAD
- support for unsupported engineering domains

IntentForge remains limited to `wall_mounted_bracket` and `l_bracket` model families.
