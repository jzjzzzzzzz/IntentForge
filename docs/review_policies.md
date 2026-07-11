# Engineering Review Policies

IntentForge review policies evaluate an existing assurance case against explicit, versioned criteria. They do not generate CAD, alter geometry, or replace the assurance record.

The flow is:

```text
ReviewPolicy
-> registered PolicyChecks
-> AssuranceCase observations
-> PolicyFindings
-> AcceptanceConditions
-> ReviewDecision
```

## Packaged policies

The initial policy manifest contains five conservative policies:

- `intentforge_static_review_v1` reviews static intent and evidence records without claiming CAD execution.
- `intentforge_standard_design_review_v1` requires run-level geometry, topology, feature-recognition, knowledge, and reasoning observations.
- `intentforge_full_design_review_v1` additionally requires artifact integrity, a valid audit package, and reproducibility metadata.
- `intentforge_edit_review_v1` requires edit-intent preservation, changed and preserved parameter traces, and regenerated geometry validation.
- `intentforge_safe_rejection_review_v1` verifies structured rejection, an explicit unsupported boundary, rejection evidence, and no CAD export.

Each policy has a stable policy ID, policy version, deterministic content ID, family and operation scope, subject type, accepted assurance profiles, checks, limitations, and a review notice.

Phase 25 does not change these five policies or their 54 checks. It records the selected policy and closed check-registry contract inside decision provenance so a later runtime can verify the exact Phase 24 semantics instead of silently applying a changed live policy.

## Scope and subjects

Policy subjects are `design_result`, `edit_result`, `safe_rejection`, or `audit_package`. Applying a policy to the wrong family, operation, or subject fails clearly. A standard-only assurance case cannot silently satisfy the full policy.

A passing safe-rejection review means the rejection handling met policy. It does not mean the unsupported design was accepted.

## Declarative safety

Policy YAML selects checks from a closed source-code registry. It cannot contain Python expressions, shell commands, arbitrary field paths, module names, callable references, or dynamic imports. Evaluation is deterministic and offline.

```bash
intentforge review policies
intentforge review policy-show intentforge_standard_design_review_v1
intentforge review policy-validate
```

Policy acceptance is an internal IntentForge decision within the declared scope. It is not regulatory approval, legal certification, structural certification, a safety guarantee, or production authorization.
