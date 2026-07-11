# Policy Checks

Review checks are typed, registered evaluators over an assurance case. The packaged manifest can configure only known parameters for each check type. Unknown parameters and unsupported identifiers fail validation.

## Check groups

Profile and schema checks:

- `assurance_profile_allowed`
- `minimum_assurance_profile`
- `overall_assurance_status_allowed`
- `schema_version_supported`

Claim and validation checks:

- `required_claim_present`
- `required_claim_status`
- `forbidden_claim_status`
- `maximum_partial_claim_count`
- `zero_failed_claims`
- `zero_unresolved_claims`
- `required_validation_present`
- `required_validation_status`

Traceability and integrity checks:

- `required_evidence_status`
- `required_capability_reference`
- `required_rule_reference`
- `artifact_integrity_required`
- `audit_package_valid`
- `reproducibility_required`

Limit, rejection, and edit checks:

- `limitation_category_allowed`
- `limitation_category_forbidden`
- `limitation_requires_manual_review`
- `unsupported_boundary_disclosed`
- `safe_rejection_verified`
- `no_cad_artifact_on_rejection`
- `edit_intent_preservation_required`
- `required_review_disclosed`

## Severity and status

Severities are `informational`, `warning`, `conditional`, `manual_review`, and `blocking`. Check statuses are `passed`, `failed`, `unresolved`, `not_applicable`, and `not_checked`.

An unresolved required blocking check produces an unresolved decision. A blocking failure rejects the record under that policy. Manual-review and conditional severities produce explicit review requirements or acceptance conditions. Warning and informational checks remain visible without being misrepresented as certification failures.

Framework evidence resolution never substitutes for missing run-level geometry validation. Documentation alone cannot satisfy a runtime geometry check.
