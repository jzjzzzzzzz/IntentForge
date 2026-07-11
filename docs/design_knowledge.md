# Design Knowledge Rule System

Phase 20 adds the foundation for an engineering knowledge layer in IntentForge.

Phase 23 assurance cases reference rule and pack IDs, versions, applicability, outcomes, and provenance without duplicating the authoritative rule database.

IntentForge does not replace engineering judgment. It encodes engineering knowledge into explainable validation rules that can support review, recommendations, and design rationale.

The capability coverage layer is separate from rule evaluation. It answers which supported and unsupported capabilities are declared, which rules contribute to them, and what implementation or verification evidence backs each claim. It does not add engineering rules or change rule thresholds.

The evidence traceability layer is separate again. It resolves evidence definitions into observations, assembles capability evidence bundles, and produces deterministic trust reports for the declared scope. It does not treat documentation alone as proof of CAD behavior and does not create a generic trust score.

The knowledge layer does not generate CAD. It does not write CadQuery code, edit topology, run FEA, or claim certified safety. It provides deterministic advisory findings that can be traced back to YAML rules.

## Purpose

The knowledge layer turns engineering heuristics into structured checks:

```text
engineering knowledge
-> design rules
-> compiled constraints
-> deterministic evaluation
-> design rationale
```

This helps IntentForge explain why a generated design may be acceptable, risky, or worth revising.

## Architecture

The implementation lives under `src/intentforge/knowledge/`:

- `schema.py`: Pydantic models for rules, findings, and compiled constraints
- `provenance.py`: provenance records for source, confidence, and verification level
- `report.py`: stable JSON report schema and export helpers
- `rules.py`: YAML loader and in-memory rule registry
- `packs/`: modular, versioned rule pack schemas, loader, registry, validation, and packaged YAML data
- `compiler.py`: transforms rules into machine-readable constraints
- `evaluator.py`: evaluates declarative rule expressions against deterministic metrics
- `rationale.py`: generates Markdown rationale from knowledge findings
- `reasoning/`: connects findings into interactions, trade-offs, conflicts, priorities, and recommendations
- `evidence_schema.py`, `evidence_registry.py`, `evidence_resolver.py`, `evidence_bundles.py`, and `trust.py`: resolve evidence and build capability evidence bundles and trust reports
- `data/bracket_rules.yaml`: compatibility manifest that points to packaged rule packs

The authoritative rule data now lives in:

- `packs/data/mechanical.yaml`
- `packs/data/manufacturing.yaml`
- `packs/data/assembly.yaml`
- `packs/data/structural.yaml`

## Rule Format

Rules are data, not Python logic:

```yaml
rules:
  - id: hole_edge_margin_001
    rule_version: "1.0"
    status: active
    created_by: intentforge-team
    last_updated: "2026-07-10"
    name: Hole Edge Margin
    category: mechanical
    description: Hole edge distance is below the recommended margin.
    applies_to: [wall_mounted_bracket, l_bracket]
    condition:
      expression: "hole_edge_distance >= 1.5 * hole_diameter"
      required_metrics: [hole_edge_distance, hole_diameter]
      when:
        mounting_holes_active: true
    severity: warning
    recommendation: Increase hole edge distance or reduce hole diameter.
    source_reference: IntentForge Phase 20 initial mechanical design heuristic.
    confidence: 0.9
    reasoning:
      implications:
        - Insufficient edge margin may reduce local material support around the hole.
      affects:
        - plate_width
        - hole_spacing
      priority_weight: 0.9
      can_conflict_with:
        - hole_spacing_001
      mitigation: Increase plate width before reducing hole spacing.
```

The evaluator supports a restricted expression language for arithmetic, boolean, and comparison operations. It does not use `eval()` and does not allow function calls, attribute access, imports, or arbitrary Python execution.

Older rule YAML files without lifecycle metadata still load. IntentForge applies safe defaults:

- `rule_version: "1.0"`
- `status: active`
- `created_by: intentforge-team`
- `last_updated: "2026-07-10"`

## Rule Lifecycle

The intended rule lifecycle is:

```text
Draft
-> Validated
-> Active
-> Deprecated
```

Only `active` and `deprecated` are currently encoded in the stable schema. Draft and validated states are workflow concepts used before a rule enters the packaged rule database.

Active rules are evaluated. Deprecated rules may remain in the database for traceability but are not applied by the evaluator.

## Confidence Model

Confidence does not mean mathematical proof.

It represents the reliability of the engineering knowledge source and the fit of the heuristic to IntentForge's supported model families. A confidence value near `1.0` means the rule is considered a stronger design heuristic. It still does not imply simulation accuracy, certification, or guaranteed safety.

## Reproducibility

Engineering reports must be reproducible.

The same intent, same parameter table, same feature flags, same rule IDs, and same rule versions should produce the same knowledge findings. Rule IDs are stable human-readable identifiers such as:

```text
hole_edge_margin_001
```

IntentForge does not generate random rule IDs. JSON knowledge report IDs are derived deterministically from checked rule IDs, rule versions, pass/fail states, and severities.

Engineering reasoning reports add a separate reproducibility dimension:

```text
Rule version: hole_edge_margin_001 v1.0
Reasoning engine version: 1.0
```

The same knowledge report, same rule metadata, and same reasoning engine version should produce the same reasoning report ID.

## Initial Rule Categories

The initial rules cover:

- mechanical hole edge margin and hole spacing
- L-bracket gusset recommendation
- corner-radius recommendation
- manufacturing tool clearance and simplicity
- assembly fastener accessibility and installation difficulty
- structural cutout stiffness tradeoff
- thin-section warning

## CLI Usage

List loaded engineering rules:

```bash
python -m intentforge.cli knowledge list
```

Validate packaged rules:

```bash
python -m intentforge.cli knowledge validate
```

Inspect and validate rule packs:

```bash
python -m intentforge.cli knowledge packs
python -m intentforge.cli knowledge packs-validate
```

Inspect and validate reasoning metadata:

```bash
python -m intentforge.cli knowledge reasoning-info
python -m intentforge.cli knowledge reasoning-validate
python -m intentforge.cli knowledge reasoning-verify
```

Generate a design review with knowledge findings:

```bash
python -m intentforge.cli design-review wall_mounted_bracket --knowledge
python -m intentforge.cli design-review l_bracket --knowledge
```

Generate a design review with deterministic engineering reasoning:

```bash
python -m intentforge.cli design-review wall_mounted_bracket --knowledge --reasoning
python -m intentforge.cli design-review l_bracket --knowledge --reasoning
```

Write both Markdown rationale and standalone JSON knowledge report:

```bash
python -m intentforge.cli design-review wall_mounted_bracket --knowledge --json
python -m intentforge.cli design-review wall_mounted_bracket --knowledge --reasoning --json
```

Knowledge-enhanced design review writes:

```text
output/design_review_report.json
output/design_review_summary.md
output/design_knowledge_rationale.md
output/knowledge_report.json
output/engineering_reasoning_report.md
output/engineering_reasoning_report.json
output/design_review_runs/<run_id>/
```

## Limitations

- Rules are heuristics, not simulation.
- No FEA, load rating, fatigue analysis, or manufacturing-process certification is performed.
- The rule database is intentionally small and deterministic.
- Rule packs organize the existing database; they do not expand support beyond the two bracket families.
- Findings are advisory unless future phases promote specific rules into strict quality gates.
- The current metrics are derived from IntentForge parameter tables and feature flags, not arbitrary imported CAD.
- Engineering reasoning is deterministic and advisory; it does not execute CAD, call an LLM, run FEA, or certify safety.
