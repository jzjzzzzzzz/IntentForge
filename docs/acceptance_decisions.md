# Acceptance Decisions

A `ReviewDecision` is the structured result of applying one validated review policy to one validated assurance case. It records one finding per policy check, outstanding conditions, exact reference IDs, decision counts, policy and assurance identities, and a deterministic decision ID.

## Decision statuses

- `accepted_within_declared_scope`: all required checks passed and no higher-priority finding remains.
- `accepted_with_conditions`: a conditional finding requires recorded action but no blocking or manual-review finding exists.
- `manual_review_required`: a policy-designated limitation or observation requires external review.
- `rejected_by_policy`: a blocking check failed.
- `unresolved`: a required blocking check could not be evaluated or was not checked.

Decision precedence is fixed:

1. unresolved required blocking check
2. failed blocking check
3. manual-review finding
4. conditional finding
5. all required checks passed

Warnings and informational findings do not silently override blocking checks. There is no combined confidence or trust score.

## Determinism

Finding, condition, policy, and decision IDs use canonical JSON content hashes. Runtime timestamps, request IDs, run timestamps, and temporary output locations are not part of decision identity. Policy versions, assurance claim states, validation observations, limitations, artifact hashes, and policy check content are semantic inputs and can change the decision identity.

## CLI

```bash
intentforge review evaluate output/assurance/assurance_case.json \
  --policy intentforge_standard_design_review_v1
intentforge review validate output/assurance/review_decision.json
intentforge review show output/assurance/review_decision.json
intentforge review render output/assurance/review_decision.json
intentforge review compare decision-a.json decision-b.json
```

Evaluation exit codes are:

- `0`: accepted within declared scope
- `2`: accepted with conditions
- `3`: manual review required
- `4`: rejected by policy
- `5`: unresolved or invalid review input

These statuses describe policy conformance for the recorded run. They do not certify the design for external use.
