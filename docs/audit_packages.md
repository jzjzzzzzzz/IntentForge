# Audit Packages

An IntentForge audit package is a portable directory containing a structured assurance case and the snapshots needed to inspect it without an opaque summary.

The package contains `manifest.json`, JSON and Markdown assurance records, intent, capability and evidence snapshots, validation and reasoning summaries, an artifact manifest, and checksums. Metadata-only and dry-run packages are supported; CAD binaries are not required.

Package validation checks required files, schema compatibility, assurance identifiers, safe relative paths, per-file hashes, logical package identity, and referenced capability, evidence, and rule IDs. Absolute paths, traversal, `.git`, `.claude`, and `CLAUDE.md` are rejected.

The logical package ID is deterministic for identical logical content. Physical archive byte identity is not claimed because this phase exports directories rather than a canonical archive format.

Review files are optional. A Phase 25 package may additionally contain `review_policy_snapshot.json`, `review_decision.json`, `review_decision.md`, and `review_decision_provenance.json`. A Phase 26 package also contains `review_policy_catalog_snapshot.json`, which freezes all five native policies and 54 declarative checks. All files are checksummed and cross-validated against the assurance case, policy, decision, provenance IDs, and deterministic static replay result. Adding a review decision intentionally creates a new logical package identity.

Phase 26 package schema `1.1` uses the `intentforge_portable_audit_v1` profile. JSON key order, indentation, encoding, line endings, safe relative paths, runtime identifiers, timestamps, timezones, and host metadata are normalized before hashing. Existing Phase 23 packages without review files, Phase 24 packages with the original three review files, and Phase 25 packages with provenance remain valid through the normal validator; only schema `1.1` packages can claim isolated offline verification.

```bash
intentforge assurance package output/assurance/assurance_case.json
intentforge assurance package-validate output/assurance/audit_package_<case-id>
intentforge assurance package-inspect output/assurance/audit_package_<case-id> --json
intentforge review verify-offline output/assurance/audit_package_<case-id>
```

Audit packages provide evidence-backed records within IntentForge's declared scope. They do not certify safety, manufacturability, regulatory approval, or fitness for a particular external use.

See [Offline verification](offline_verification.md) and [Audit portability](audit_portability.md) for the static trust boundary and cross-platform identity rules.
