# Validation

IntentForge validates both geometry and design intent.

Assurance validation is additive to geometry validation. It checks record integrity, reference validity, profile-required observations, safe artifact paths, and deterministic content IDs; it does not rerun or weaken existing CAD validators.

Review-policy validation is additive to assurance validation. It checks policy IDs and versions, scope, registered check types, type-specific parameters, referenced claim/validation/capability/evidence/rule identifiers, deterministic policy and decision IDs, and decision precedence. Policy evaluation reads existing assurance observations and does not rerun CAD generation.

Decision-provenance validation checks every frozen snapshot and execution-node content ID, the check-registry and precedence contracts, the 65-definition evidence matrix, policy and assurance links, and optional deterministic replay. Audit-package validation also cross-checks the standalone provenance file and package manifest. Structural decision diffs validate their own delta, pairwise-report, and multi-variant logical identities; they do not use report prose as evidence.

Phase 26 offline verification starts with package entry and SHA-256 checks, then validates canonical JSON and platform-neutral data before replaying the selected closed policy from frozen snapshots. It validates all 54 catalog checks structurally and evaluates only the policy selected for that run. This static verification does not rerun geometry, topology, feature recognition, reasoning, or simulation.

Phase 27 CAS validation checks every structural object address, the canonical envelope address, manifest binding, and predecessor consistency across assurance claims, the assurance case, review decision, provenance snapshot/node, and CAS envelope. Chain validation applies isolated package verification to each predecessor and rejects missing, modified, switched, cyclic, or mismatched history blocks.

Phase 21 adds capability coverage validation. This is not geometry validation. It validates product support declarations: known families, valid stages, rule-to-capability mapping, evidence references, unsupported boundaries, and orphan active rules.

## Geometry Validation

Geometry validation checks the generated CadQuery model against the parameter table. Current checks include:

- positive parameter ranges
- bounding-box width, height, and thickness
- L-bracket bounding-box base leg, vertical leg, and bracket width
- mounting-hole spacing limits
- mounting-hole diameter limits
- L-bracket base and vertical hole spacing limits
- L-bracket gusset dimension limits when active
- center cutout inside plate limits
- corner radius limits
- edge fillet radius limits
- exported STEP/STL file existence and size
- topology metrics in validation metadata when CadQuery inspection is available
- feature recognition metadata for supported generated features
- optional engineering knowledge findings in design review reports
- optional engineering reasoning reports in design review reports

Bounding-box checks use the generated CadQuery model. Hole, cutout, and L-bracket per-leg hole sizing checks remain parameter-based, with topology-informed feature recognition recorded separately in report metadata.

## Feature Recognition Metadata

Phase 18 adds topology-informed feature recognition to geometry validation metadata:

```text
validation_report.metadata["feature_recognition"]
```

The recognizer inspects CadQuery/OpenCascade topology where available:

- cylindrical face candidates for through holes
- internal planar faces near the center cutout
- solid count and validity for connected L-bracket legs
- sloped planar faces for triangular gussets where practical
- basic face, edge, and solid topology consistency

Feature recognition is conservative. If the recognizer is not confident, it records structured warnings instead of pretending success. Ordinary validation does not crash when recognition cannot be completed.

## Intent Validation

Intent validation checks whether the structured design state is internally consistent. It verifies:

- object type is `wall_mounted_bracket`
- object type is `l_bracket` for L-bracket prompts
- required parameters exist
- required constraints exist
- active feature plan steps exist
- mounting-hole pattern matches hole count
- L-bracket hole counts are 0 or 2 per leg
- L-bracket legs are created and joined before cuts, gussets, or fillets
- base plate is created before cuts
- requested center cutout appears in the feature plan

## Current Limits

IntentForge does not perform full industrial CAD feature recognition from
arbitrary solids. Bracket recognition remains the detailed Phase 18 path. The
registered flange validator reports conservative topology-informed observations
for a single connected ring solid, central bore, and polar through-hole pattern;
it does not infer pressure-class or standards compliance.

For L-brackets, inside fillet intent is represented in parameters and validation, but robust geometric inside-corner filleting is future work.

## Engineering Knowledge Findings

Phase 20 adds deterministic engineering knowledge findings to design review reports when requested with `--knowledge`.

These findings are based on YAML rules and parameter-derived metrics. They provide recommendations such as hole edge margin, hole spacing, cutout stiffness tradeoff, and gusset advisories. They are not FEA results, safety certification, or a replacement for engineering review.

Phase 20.6 adds deterministic engineering reasoning when requested with `--knowledge --reasoning`.

Reasoning connects knowledge findings into rule interactions, trade-offs, conflicts, priorities, and advisory recommendations. It remains separate from CAD generation and does not modify geometry automatically.

Phase 20.7 adds golden-case reasoning verification. The verification layer checks expected deterministic report IDs, expected interactions and conflicts, recommendation contradictions, and recommendation applicability. These checks are included in the technical harness quality gates.

Phase 20.8.1 adds rule-pack validation. The knowledge rules are grouped into mechanical, manufacturing, assembly, and structural packs. Pack validation checks metadata, duplicate pack IDs, duplicate rule IDs, unsupported categories, unsupported model families, unknown rule references, and legacy manifest compatibility. The technical harness includes lightweight rule-pack quality gates.

Phase 22 adds evidence validation and trust reporting. Evidence validation checks evidence IDs, roles, types, references, family and stage applicability, unknown capability/rule/pack references, boundary rejection evidence, limitation evidence, and deterministic bundle/report IDs. It does not execute YAML-selected code or treat unresolved evidence as verified.
