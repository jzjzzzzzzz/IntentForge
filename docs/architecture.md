# Architecture

## Declarative Topology Registry

Phase 32 separates topology metadata from runtime adapters:

```text
packaged manifest
-> TopologyManifest validation
-> RegistryManager
-> registry-derived intent schema
-> closed parser/factory/validator adapter
-> existing validation, knowledge, assurance, CAS, and dossier pipeline
```

Manifests are declarative data. They cannot name arbitrary Python modules or
callables. Adapter identifiers must exist in closed code-side registries. Safe
arithmetic formulas use a restricted AST containing names, numeric constants,
addition, subtraction, multiplication, division, and unary signs only.

The authoritative manifests live under
`intentforge/knowledge/topology/families/<family>/manifest.yaml`. Runtime
registry code lives under `intentforge/topology/` so parser startup does not
eagerly initialize benchmark and reporting modules.

IntentForge is organized as a deterministic CAD intent pipeline. Each module owns one part of the path from prompt to validated CAD.

The per-design assurance layer adapts existing workflow responses into structured claims, arguments, validation observations, capability/evidence references, limitations, and safe artifact records. It does not execute a second CAD pipeline. Deterministic renderers and audit-package validation operate on the authoritative structured assurance case.

The review-policy layer consumes a validated assurance case. Packaged declarative policies select checks from a closed evaluator registry, producing structured findings, conditions, and a deterministic review decision. It does not rerun CAD generation, mutate assurance records, or execute policy-provided code.

The Phase 25 provenance layer freezes policy, assurance, rule, capability, evidence, package, boundary, check-registry, and precedence inputs alongside the ordered execution graph. Replay uses these snapshots instead of live manifests. The differential-audit layer compares keyed graph nodes, checks, findings, conditions, references, and outcomes; rendered Markdown is never used as comparison input.

The Phase 26 portability boundary creates a normalized export copy without mutating the live run record. Reviewed packages add a frozen catalog of all five policies and 54 checks. `intentforge.offline_verify` is an isolated standard-library verifier that checks package inventory, canonical serialization, frozen registry references, selected policy evaluation, precedence, and provenance without importing CadQuery, Pydantic models, live registries, or network clients.

The Phase 27 CAS boundary assigns full SHA-256 addresses to structural package files and to a canonical envelope over those objects. `intentforge.cas` stores verified packages under deterministic digest paths and follows optional predecessor addresses to verify chronological lineage. A predecessor is a recorded content reference only; the CAS layer never executes CAD, policies, or manifest-selected code.

Importable Python packages use a `src/` layout:

- `src/intentforge`
- `src/mcp_server`
- `src/benchmark`
- `src/harness`

Project assets such as `tests/`, `docs/`, `examples/`, and `demo/` remain at the repository root.

## Core Modules

`intentforge.schemas` defines Pydantic models for intent, parameters, constraints, feature plans, validation reports, and edit reports. These schemas are the contract between pipeline stages.

`intentforge.parser` contains deterministic regex-based parsers for initial CAD prompts and natural-language edit requests. The parser supports wall-mounted bracket / mounting-plate requests and the Phase 10 L-bracket family.

`intentforge.features` normalizes family-aware feature flags. Wall-bracket flags cover mounting holes, center cutouts, rounded corners, and edge fillets. L-bracket flags cover base and vertical legs, per-leg holes, inside/outside fillets, and the optional triangular gusset.

`intentforge.planner` creates feature history plans from active feature flags. The plan records which features are built, in which order, and why.

`intentforge.generator` builds CadQuery geometry from the parameter table and feature flags. It reads important dimensions from named parameters rather than hard-coded CAD dimensions. Family dispatch currently routes to `build_wall_bracket` or `build_l_bracket`.

`intentforge.validator` checks geometry and intent. Geometry checks are parameter and bounding-box driven. Intent checks verify object type, required parameters, feature ordering, and pattern consistency.

`intentforge.knowledge` loads YAML engineering rules, compiles them into machine-readable constraints, evaluates parameter-derived metrics, generates Markdown rationale, and builds deterministic engineering reasoning reports. It does not generate or modify CAD.

`intentforge.knowledge.packs` is the rule-pack management layer. It loads modular package-data YAML packs, validates pack metadata, detects duplicate rule IDs, maps rules back to source packs, and flattens packs into the existing `DesignKnowledgeRule` interface used by the compiler, evaluator, and reasoning engine.

`intentforge.knowledge.capabilities` and `intentforge.knowledge.coverage` describe product support claims as deterministic data. The capability manifest maps supported, partially supported, and explicitly unsupported boundaries to CAD families, pipeline stages, knowledge packs, rule IDs, and implementation or verification evidence. It does not duplicate engineering rule formulas or CAD generation logic.

`intentforge.knowledge.evidence_*` and `intentforge.knowledge.trust` resolve capability evidence references into structured observations, capability evidence bundles, and deterministic trust reports. This layer validates evidence IDs, roles, families, stages, rule references, pack references, boundary evidence, limitation evidence, and packaged resources. It does not execute manifest-selected code or make broad AI trust claims.

`intentforge.knowledge.reasoning` connects evaluated knowledge findings into interactions, trade-offs, conflicts, priorities, and advisory recommendations. The reasoning package has no CadQuery or LLM dependency.

`intentforge.knowledge.reasoning.verification` runs packaged golden engineering cases to check deterministic report IDs, expected reasoning behavior, recommendation contradictions, and recommendation applicability. It is a verification layer only; it does not modify CAD or rules.

`intentforge.assurance` builds run-level Claims-Arguments-Evidence records and safe directory audit packages from existing workflow outputs.

`intentforge.review` loads versioned review policies, validates typed checks and references, evaluates assurance observations, freezes and replays decision provenance, renders acceptance decisions, performs structural pairwise or multi-variant diffs, and optionally attaches policy, decision, and provenance snapshots to audit packages.

`intentforge.offline_verify` validates portable package schemas `1.1` and `1.2` from enclosed bytes only. It is intentionally outside the eager `intentforge.review` import surface so `python -S` can load it without site packages.

`intentforge.cas` is a standard-library storage and chain-verification layer over the isolated package verifier. It rejects different bytes at an occupied address and returns structured chain failures for missing, modified, switched, cyclic, or mismatched predecessors.

`intentforge.editor` applies structured edits to an existing parameter table and feature state. It preserves unchanged parameters and rejects unsupported or invalid edits before CAD export.

`intentforge.workflows` contains shared orchestration used by both the CLI and MCP wrapper. This keeps command-line and agent-tool behavior aligned.

`mcp_server` exposes a thin optional MCP wrapper around the workflow functions. It does not duplicate parser, generator, validator, or editor logic.

`benchmark` contains deterministic regression cases and a runner that exercises parsing, CAD generation, validation, edits, rejection behavior, and traceability.

## Output Flow

Commands write latest convenience outputs and persistent run directories. Persistent directories include prompt text, structured artifacts, run metadata, CAD exports where applicable, and validation or edit reports.
