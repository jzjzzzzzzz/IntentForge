# Engineering Assurance Cases

IntentForge assurance cases are deterministic, per-run Claims-Arguments-Evidence records. They connect an accepted request, structured intent, rule evaluation, compiled constraints, runtime validation observations, declared capabilities, project evidence, artifacts, and limitations without claiming regulatory certification.

## Profiles

- `static` records parsing, intent-schema, capability, rule, evidence, and limitation traceability. It does not claim that CAD was generated or validated.
- `standard` adapts the existing parse-build or edit workflow and records geometry, topology, feature-recognition, knowledge, and reasoning observations that actually ran.
- `full` adds artifact integrity claims when generated files have verified content hashes. It does not invent reproduction results.

## Claims and observations

A project-level capability or evidence bundle describes what the framework supports. A run-level claim is supported only when the assurance case contains the required observation. For example, `geometry_valid` requires an actual geometry-validation observation; a capability declaration alone is insufficient.

Intentional rejection is a valid scoped outcome. It records the rejection boundary, evidence references, and no-CAD-export behavior rather than representing the unsupported design as generated geometry.

## Determinism and limits

Content IDs use canonical JSON hashing. Runtime timestamps, run IDs, and request IDs do not change logical content identity. Assurance remains limited to the two supported bracket families and the checks actually executed. External engineering review remains required for load-specific, manufacturing, regulatory, or safety decisions.

```bash
intentforge assurance build --profile static
intentforge assurance build --profile standard --dry-run
intentforge assurance validate output/assurance/assurance_case.json
intentforge assurance show output/assurance/assurance_case.json
```
