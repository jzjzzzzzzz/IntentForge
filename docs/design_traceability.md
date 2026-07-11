# Design Traceability

Phase 24 extends run traceability with a separate review decision. The assurance case remains the authoritative record of observations; the selected policy records which observations were required and why the resulting acceptance, condition, manual-review, rejection, or unresolved status occurred.

Phase 23 connects one design request to its structured outcome:

```text
request -> intent -> feature plan -> constraints -> rules -> validation
        -> capabilities -> evidence -> assurance claims -> audit package
```

Rule references retain rule and pack versions, applicability, evaluation outcome, affected parameters, and provenance. Constraint summaries preserve only data exposed by the existing constraint graph; missing units or validation outcomes are reported as not checked rather than invented. Artifact records contain safe relative paths, logical names, hashes where files exist, producer operations, and validation status.

Assurance comparison reports structured changes in intent, features, constraints, rules, validation observations, limitations, artifact hashes, and overall status. It does not perform geometric visual comparison.

Edit assurance adapts the existing edit parser and application workflow. Safe rejection assurance adapts existing structured errors and rejection evidence. Neither path changes CAD geometry or expands declared capability scope.
