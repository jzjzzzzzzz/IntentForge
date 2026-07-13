# Hash-Chained Audit Lineage

## Model

A finalized package may name one prior package with `predecessor_hash_pointer`. A package without a predecessor is a genesis record. Each successor embeds the same full predecessor address in:

- every assurance claim and argument
- the assurance case
- the review decision
- a dedicated frozen provenance snapshot
- a lineage-binding provenance execution node
- the CAS envelope and package manifest

The successor package's own content address covers that pointer. Changing the pointer therefore creates a different package identity.

This is a local chronological hash-linked ledger. It is not a distributed blockchain, consensus protocol, cryptocurrency system, database, or network service.

## Building and Tracking

Create a full reviewed package and store it:

```bash
intentforge review build-evaluate --profile full \
  --family wall_mounted_bracket \
  --cas-store output/review-cas
```

Create a successor from either a verified package directory or its full hash:

```bash
intentforge review build-evaluate --profile full \
  --family l_bracket \
  --predecessor output/previous-run/review/audit_package \
  --cas-store output/review-cas
```

The predecessor option is restricted to review policies that produce an audit package. It does not alter CAD geometry or add a new generation path.

## Verification

```bash
intentforge review chain-verify <head-package> --store output/review-cas
intentforge review chain-verify <head-package> --store output/review-cas --json
```

Verification starts at the head, runs isolated package verification for every block, checks the package address against the expected predecessor pointer, and follows the store's deterministic address path until genesis. The result includes chronological addresses and a deterministic chain content address.

The verifier fails when:

- predecessor bytes are modified
- an expected predecessor is deleted
- another valid package is switched into the expected hash location
- a pointer is malformed or mismatched
- a package or CAS envelope fails static verification
- a cycle is encountered
- the configured maximum depth is exceeded

## Edit Lineage

An edit review can point to the package for the prior design run. This complements, but does not replace, the existing parent-run and intent-preservation records. The hash pointer identifies exact prior audit content; edit traceability still describes changed and preserved engineering intent.

## Trust Boundary

Chain verification proves internal hash linkage for the packages available in the selected CAS store. It does not prove that every real-world event was recorded, identify an author, establish legal custody, or certify an engineering design. Deleting an unreferenced branch is outside a single-head chain check; applications managing multiple heads must retain their own head registry or signature policy.
