# Offline Audit Package Verification

## Purpose

Phase 26 verifies a reviewed IntentForge audit-package directory using only the files enclosed by that package. The verifier is implemented with the Python standard library and does not load current rule, capability, evidence, or policy manifests.

```bash
intentforge review verify-offline output/assurance/audit_package
intentforge review verify-offline output/assurance/audit_package --json
```

The standalone library entry point is:

```python
from intentforge.offline_verify import verify_offline_audit_package

result = verify_offline_audit_package("audit-package")
```

## Verification Order

The verifier fails in ordered stages:

1. Package entry names, required files, symlinks, and nested paths.
2. Checksum block and logical file inventory.
3. Duplicate JSON keys, UTF-8, canonical JSON, and Markdown line endings.
4. Portable paths, runtime metadata, timestamps, and normalized IDs.
5. Assurance, policy, evidence, decision, and provenance identities.
6. Closed policy-check replay and final decision precedence.

Checksum failures stop verification before untrusted structured payloads are used for static replay.

## Frozen Scope

A Phase 26 reviewed package contains:

- 10 frozen engineering rules and their pack sources
- 28 frozen capability definitions
- 65 frozen evidence definitions and 65 matching observations
- all five native review policies and 54 declarative checks
- the selected policy and its findings, conditions, and ordered execution nodes
- the assurance claims that apply to the specific run

The technical harness uses five fixture packages whose run-specific assurance records total 49 claims. A single package contains only the claims relevant to that run; it does not contain unrelated fixture claims.

## Static Replay

The verifier independently evaluates the selected policy's closed check types from frozen data, reconstructs finding and condition identities, applies the recorded blocking precedence, and validates the decision and provenance content IDs. All 54 catalog checks are schema- and identity-validated; only the selected policy is applied to a specific assurance case.

The verifier does not:

- rerun CadQuery or regenerate geometry
- rerun simulation, FEA, or manufacturing analysis
- access a network
- dynamically import a verifier named by package data
- execute commands or callables from JSON or YAML
- use an LLM
- provide regulatory or safety certification

## Tamper Detection

The package records SHA-256 hashes for each enclosed payload and a deterministic logical package ID. Modified files, stale snapshot IDs, changed findings, altered policy results, unsafe paths, and inconsistent inventories fail validation.

This is integrity checking for the enclosed deterministic record. It is not a digital signature or proof against an attacker who can replace the entire package and every external trust anchor. Signed distribution is outside Phase 26.

## Compatibility

Phase 23 through Phase 25 packages remain readable by the normal audit-package validator. The isolated Phase 26 verifier requires package schema `1.1`, the frozen policy catalog, and portability metadata. It reports older packages as unsupported rather than treating missing data as verified.
