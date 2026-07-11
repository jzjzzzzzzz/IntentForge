# Audit Packages

An IntentForge audit package is a portable directory containing a structured assurance case and the snapshots needed to inspect it without an opaque summary.

The package contains `manifest.json`, JSON and Markdown assurance records, intent, capability and evidence snapshots, validation and reasoning summaries, an artifact manifest, and checksums. Metadata-only and dry-run packages are supported; CAD binaries are not required.

Package validation checks required files, schema compatibility, assurance identifiers, safe relative paths, per-file hashes, logical package identity, and referenced capability, evidence, and rule IDs. Absolute paths, traversal, `.git`, `.claude`, and `CLAUDE.md` are rejected.

The logical package ID is deterministic for identical logical content. Physical archive byte identity is not claimed because this phase exports directories rather than a canonical archive format.

Review files are optional. A Phase 25 package may additionally contain `review_policy_snapshot.json`, `review_decision.json`, `review_decision.md`, and `review_decision_provenance.json`. All files are checksummed and cross-validated against the assurance case, policy, decision, provenance IDs, and deterministic replay result. Adding a review decision intentionally creates a new logical package identity. Existing Phase 23 packages without review files and Phase 24 packages with the original three review files remain valid; only Phase 25 packages can claim frozen replay provenance.

```bash
intentforge assurance package output/assurance/assurance_case.json
intentforge assurance package-validate output/assurance/audit_package_<case-id>
intentforge assurance package-inspect output/assurance/audit_package_<case-id> --json
```

Audit packages provide evidence-backed records within IntentForge's declared scope. They do not certify safety, manufacturability, regulatory approval, or fitness for a particular external use.
