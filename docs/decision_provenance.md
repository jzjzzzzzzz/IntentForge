# Review Decision Provenance

## Purpose

Decision provenance freezes the deterministic inputs and execution chain used to produce one `ReviewDecision`. It allows a downstream reviewer to verify what was evaluated even if a live rule pack, capability declaration, evidence manifest, or policy later changes.

The provenance record does not preserve executable Python code. It records validated declarative snapshots and explicit engine-contract versions. A future runtime may replay the record only when it still implements the recorded evaluator, check-registry, and precedence contracts. An incompatible runtime reports `unsupported`; it does not reinterpret the decision.

## Frozen Inputs

Each new decision records ten deterministic snapshots:

- review policy, including every typed check and parameter
- assurance case
- all 10 engineering rules and their pack sources
- all 28 declared capabilities
- all 65 evidence definitions
- one static evidence observation per evidence definition
- closed check-registry contract
- decision precedence strategy
- audit-package observation supplied to policy checks
- active run boundary conditions

Evidence that was not selected by the reviewed case remains in the matrix with `not_checked` status. Static provenance does not claim runtime verification for those entries.

## Execution Chain

Ordered execution nodes record assurance validation, subject resolution, scope validation, evidence resolution, one node per policy check, final precedence, and decision assembly. Each node has a stable node key, status, typed parameters, observed and expected values, input/output content IDs, and a deterministic node ID.

Runtime timestamps and request metadata are excluded from provenance identity. Identical deterministic inputs produce identical snapshot, node, provenance, and decision IDs.

## Replay

```bash
intentforge review provenance review_decision.json
intentforge review provenance review_decision.json --verify
intentforge review provenance audit_package_directory --verify --json
```

Replay reconstructs the policy, assurance case, rule IDs, capability IDs, evidence definitions, evidence observations, package observation, and check context exclusively from the frozen record. It does not reload live knowledge manifests. Snapshot tampering, execution-node tampering, evidence-matrix misalignment, content-ID mismatch, or replay identity mismatch fails verification.

## Audit Packages

Decision-bearing audit packages include `review_decision_provenance.json`. Its checksum, provenance ID, content ID, embedded decision reference, and replay result are validated with the rest of the package. Older Phase 24 packages containing only the policy and decision files remain loadable, but they cannot claim Phase 25 replay provenance.

## Limitations

Provenance verifies deterministic policy execution within the recorded IntentForge contract. It does not prove structural safety, manufacturability, certification, or correctness outside the two declared bracket families. It does not preserve arbitrary source code or execute code selected by a manifest.
