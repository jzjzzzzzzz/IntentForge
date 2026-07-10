# Knowledge Rule Packs

Phase 20.8.1 organizes IntentForge engineering knowledge into modular, versioned rule packs.

Rule packs are data. They do not execute code, generate CAD, call an LLM, run FEA, or certify a design. They group existing engineering heuristics so the knowledge database is easier to maintain, validate, package, and audit.

## Purpose

Rule packs organize engineering knowledge into stable groups:

```text
rule pack YAML
-> RulePack loader
-> RulePackRegistry
-> flattened DesignKnowledgeRule list
-> existing RuleRegistry
-> compiler / evaluator / reasoning
```

Downstream evaluation and reasoning still consume `DesignKnowledgeRule` objects. The pack layer is a management layer above the existing flattened rule interface.

Phase 21 adds a separate capability manifest. That manifest describes product support claims and points to rule packs, rule IDs, implementation evidence, and verification evidence. It does not become a second engineering rule database.

## Structure

Each pack includes:

- `pack_id`: stable identifier such as `bracket_mechanical`
- `pack_version`: pack lifecycle version such as `1.0`
- `category`: one of `mechanical`, `manufacturing`, `assembly`, or `structural`
- `supported_model_families`: currently `wall_mounted_bracket` and `l_bracket`
- `status`: `active` or `deprecated`
- `rules`: existing `DesignKnowledgeRule` entries
- `metadata`: non-executable traceability metadata

Rules keep their own stable IDs and rule versions. Moving a rule into a pack does not change the rule ID, condition, recommendation, confidence, provenance, or reasoning metadata.

## Current Packs

The current source of truth is:

- `src/intentforge/knowledge/packs/data/mechanical.yaml`
- `src/intentforge/knowledge/packs/data/manufacturing.yaml`
- `src/intentforge/knowledge/packs/data/assembly.yaml`
- `src/intentforge/knowledge/packs/data/structural.yaml`

Current active packs:

| Pack ID | Version | Category | Rules |
| --- | --- | --- | ---: |
| `bracket_mechanical` | `1.0` | mechanical | 4 |
| `bracket_manufacturing` | `1.0` | manufacturing | 2 |
| `bracket_assembly` | `1.0` | assembly | 2 |
| `bracket_structural` | `1.0` | structural | 2 |

Total active rules remain 10.

## Backward Compatibility

The legacy file:

```text
src/intentforge/knowledge/data/bracket_rules.yaml
```

is now a compatibility manifest that references the four rule packs. Existing callers of `load_rules()` and `RuleRegistry.load()` still receive the same flattened 10 active rules in deterministic order.

The compatibility manifest is not an independent rule database. This avoids maintaining duplicate authoritative YAML content.

## Validation

Validate rule packs with:

```bash
python -m intentforge.cli knowledge packs
python -m intentforge.cli knowledge packs-validate
```

Validation checks include:

- duplicate pack IDs
- duplicate rule IDs inside or across packs
- invalid pack status
- unsupported category
- unsupported model family
- empty rule lists
- rule category mismatch
- invalid rule metadata
- invalid reasoning metadata
- unknown referenced rule IDs

## Versioning

IntentForge separates several version concepts:

- package version: the installable Python package version
- pack version: version of a grouped rule pack
- rule version: version of an individual engineering rule
- reasoning engine version: version of deterministic reasoning behavior

This separation supports reproducibility. The same input, same rule IDs, same rule versions, same pack versions, and same reasoning engine version should produce the same knowledge and reasoning results.

Capability manifest version is another separate concept. It versions support declarations, not engineering formulas.

## Packaging

Rule pack YAML files are package data and are included in the wheel and source distribution. The loader uses package resources, so packs can load from:

- source checkout
- editable install
- installed wheel

No repository-relative path is required for default pack loading.

## Limitations

- Current packs contain bracket knowledge only.
- Supported CAD families remain `wall_mounted_bracket` and `l_bracket`.
- Rule packs are not certification packages.
- Rules remain heuristic or reference-backed according to their provenance.
- Packs do not dynamically execute code.
- Unsupported engineering domains remain unsupported until deliberately modeled and validated.
