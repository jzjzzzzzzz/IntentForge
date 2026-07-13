# Content-Addressed Audit Packages

## Purpose

Phase 27 gives every finalized reviewed audit package a full SHA-256 content address. The address is derived from canonical structural payloads, not a random UUID, timestamp, database sequence, directory name, or host path.

```text
sha256:<64 lowercase hexadecimal characters>
```

The package manifest uses this address as its primary `package_id` and `package_content_address`.

## CAS Envelope

`cas_envelope.json` contains:

- envelope schema and hash algorithm
- package content address
- optional predecessor content address
- assurance-case and review-decision IDs
- CAD family and operation
- installed IntentForge package version
- one content-addressed object record for every structural payload

Each object record names a safe logical file, its role, and the SHA-256 address of its exact bytes. Current objects include the assurance case, intent, capability/evidence snapshots, validation and reasoning summaries, artifact manifest, selected policy, complete policy catalog, review decision, provenance, and Markdown reports.

The CAS envelope addresses a canonical payload that excludes its own `content_address`. `manifest.json`, `checksums.json`, and `cas_envelope.json` are transport and verification records around the addressed structural object set. This avoids an impossible self-hash cycle while keeping every engineering record and report content-addressed.

## Immutable Storage

Store a verified package under its address:

```bash
intentforge review cas-check path/to/audit-package
intentforge review cas-store path/to/audit-package --store output/review-cas
```

Storage layout:

```text
<store>/sha256/<first-two-hex>/<full-64-hex>/
```

Writing the same bytes to an existing address is idempotent. Attempting to store different bytes at an occupied address fails. Immutability is enforced by content identity and conflict rejection; Phase 27 does not depend on platform-specific filesystem ACLs.

## Determinism

The package address includes canonical object paths, object roles, object hashes, the predecessor pointer, scoped run IDs, and the installed tool version. Host paths, local run IDs, timezones, temporary directories, and runtime timestamps remain excluded or normalized by the Phase 26 portability profile.

Changing any addressed structural file changes its object address and therefore the package address. Repeated finalization of identical deterministic content produces the same package address.

## Limits

Content addressing detects accidental or unauthorized changes relative to a known address. It is not a digital signature and does not establish who created a package. An external system that needs author authentication or non-repudiation must add a separately managed signature and trusted key policy.

Content integrity also does not certify CAD safety, manufacturability, regulatory compliance, or fitness for use.
