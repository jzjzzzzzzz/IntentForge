# Engineering Evidence Traceability

Phase 22 adds a deterministic evidence layer for IntentForge capability claims.

The capability manifest says what the project claims to support, partially support, or reject. The evidence manifest says what records support those claims and whether those records resolve against known project registries.

## Evidence Concepts

An evidence definition is declarative metadata:

- stable evidence ID
- evidence type
- evidence role
- reference
- CAD family
- pipeline stages
- related capability IDs
- related rule IDs and pack IDs
- expected result
- version and freshness policy
- limitations

An evidence observation is the result of resolving or verifying one evidence definition. A string reference alone is not treated as verified evidence until it resolves to a known rule, pack, capability, benchmark case, rejection case, harness gate, documentation reference, or packaged resource.

## Evidence Types

Current evidence types include:

- `rule_definition`
- `rule_pack`
- `parser_support`
- `intent_schema`
- `constraint_compiler`
- `cad_generator`
- `geometry_validator`
- `topology_inspector`
- `feature_recognizer`
- `knowledge_evaluator`
- `reasoning_case`
- `golden_case`
- `benchmark_case`
- `rejection_case`
- `regression_test`
- `technical_harness_gate`
- `documentation`
- `package_artifact`

Unknown evidence types fail validation.

## Evidence Roles

Roles are explicit:

- `implementation`: implementation artifact or supported internal identifier
- `verification`: deterministic case, test, or harness evidence
- `boundary`: rejection evidence for unsupported behavior
- `limitation`: documented limitation for partial support
- `provenance`: source traceability for rules and packs
- `packaging`: packaged runtime data evidence

Documentation alone is not accepted as sole verification evidence for supported CAD behavior.

## Static Resolution And Runtime Verification

Static resolution checks references against deterministic registries and safe package resources. It does not execute arbitrary YAML-selected code.

Runtime verification is limited to safe internal checks where available, such as rule-pack validation, capability validation, evidence manifest validation, and golden reasoning verification. Evidence that cannot be runtime-verified through a safe internal API must remain statically resolved, not falsely marked as executed.

## Safety

The evidence layer does not:

- generate CAD
- run CadQuery
- call an LLM
- run shell commands from YAML
- import arbitrary modules from manifest strings
- read arbitrary local files
- use `eval()` or `exec()`
- make network calls

## Commands

```bash
python -m intentforge.cli knowledge evidence-list
python -m intentforge.cli knowledge evidence-list --json
python -m intentforge.cli knowledge evidence-list --family wall_mounted_bracket
python -m intentforge.cli knowledge evidence-list --role verification
python -m intentforge.cli knowledge evidence-show ev_package_evidence_manifest
python -m intentforge.cli knowledge evidence-validate
python -m intentforge.cli knowledge evidence-resolve
python -m intentforge.cli knowledge evidence-resolve --json
```

## Limitations

Evidence traceability describes the declared IntentForge scope. It does not prove arbitrary engineering correctness, run FEA, certify safety, or expand CAD support beyond `wall_mounted_bracket` and `l_bracket`.
