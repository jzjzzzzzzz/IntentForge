# Audit Package Portability

## Deterministic Logical Identity

Phase 26 defines the `intentforge_portable_audit_v1` serialization profile. Identical deterministic design content produces the same canonical JSON payloads, checksum manifest, and logical package ID on Windows, macOS, and Linux.

Portable serialization normalizes:

- `\\` and `/` path separators to POSIX-style relative paths
- absolute artifact paths to approved logical `output/...` references
- request and run identifiers that do not affect design semantics
- host runtime metadata
- local timestamps and timezones
- operating-system and temporary-directory metadata

Parent-run presence remains meaningful for edit lineage. Its host-specific value is normalized while the presence or absence of a parent relationship is preserved.

## Canonical JSON

Every JSON file uses:

- UTF-8
- ASCII-safe escaping
- lexicographically sorted object keys
- fixed two-space indentation
- LF line endings
- one trailing newline

Duplicate JSON keys are rejected. Markdown must also be UTF-8 with LF line endings.

## Safe Paths

Serialized package paths must be relative and use `/`. The verifier rejects:

- Unix absolute paths
- Windows drive or UNC paths
- `..` traversal
- repeatedly encoded traversal
- symbolic links
- nested package entries
- `.git`, `.claude`, `CLAUDE.md`, and cache paths

Absolute local artifact paths may be used internally while building a run, but public audit records contain only normalized logical references.

## Identity Boundary

IntentForge guarantees deterministic logical package identity for identical deterministic content. It does not claim byte-identical ZIP archives because archive timestamps, compression libraries, and container metadata can differ. Phase 26 exports a directory package and compares canonical file bytes and logical hashes.

Runtime creation metadata, when present outside the deterministic payload, must not alter content IDs. The package tool version is read with `importlib.metadata.version("intentforge")`; the project version is not changed by this phase. Phase 27's full CAS address is calculated only after this portability normalization.

## Technical Harness

The quick technical harness normalizes Linux-, macOS-, and Windows-shaped versions of each of five assurance fixtures and requires:

- zero canonical content mismatches
- zero portability violations
- five successful isolated package verifications
- 49 aggregate run claims
- zero frozen evidence-matrix mismatches
- zero policy-catalog mismatches
- zero static policy replay mismatches
- zero package hash mismatches

These gates validate portability and record integrity. They do not expand supported CAD scope or substitute for external engineering review.
