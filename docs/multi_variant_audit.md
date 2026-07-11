# Multi-Variant Review Differential Audit

## Purpose

The differential audit compares review decisions as structured evaluation records. It does not compare Markdown wording and does not perform visual or geometric diffing.

The authoritative comparison covers:

- reviewed CAD family, operation, subject type, profile, and assurance identity
- active policy ID, version, content ID, checks, severities, requirements, and parameters
- keyed execution-graph nodes
- findings keyed by policy check ID
- conditions keyed by their source check ID
- final acceptance outcome
- capability, evidence, rule, and limitation references
- provenance engine and registry identities

## Outcome Transitions

The closed transition vocabulary is:

- `unchanged`
- `acceptance_elevated`
- `acceptance_constrained`
- `status_changed`

For example, moving from `accepted_with_conditions` to `accepted_within_declared_scope` is an acceptance elevation. This describes policy permissiveness only. It does not establish that the candidate design is universally safer or more correct.

## Pairwise And Multi-Variant Use

```bash
intentforge review diff baseline.json candidate.json
intentforge review diff baseline.json candidate.json --json
intentforge review diff baseline.json variant-a.json variant-b.json
intentforge review diff baseline-package variant-package --output review-delta.md
```

With multiple candidates, the first input remains the fixed baseline. Each pairwise diff is deterministic and independent of candidate argument order. The report includes an outcome matrix and security/compliance-relevant delta count without combining dimensions into an opaque score.

## Deterministic Identity

Every semantic delta has a category, stable entity key, change type, structured before/after values, changed fields, compliance impact, security relevance, summary code, content ID, and delta ID. Pairwise and multi-variant reports have separate deterministic logical identities. Runtime metadata is excluded.

## Security Boundary

The engine uses only typed Python models and closed deterministic logic. It performs no LLM call, dynamic import, manifest-selected function execution, shell command, network call, `eval()`, or `exec()`. A decision JSON or audit-package directory is data, never executable configuration.

## Limitations

The audit describes recorded policy and assurance differences. It does not infer missing observations, simulate loads, compare CAD visually, authorize production, or provide regulatory certification.
