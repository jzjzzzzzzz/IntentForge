# Design Knowledge Rule System

Phase 20 adds the foundation for an engineering knowledge layer in IntentForge.

IntentForge does not replace engineering judgment. It encodes engineering knowledge into explainable validation rules that can support review, recommendations, and design rationale.

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
- `rules.py`: YAML loader and in-memory rule registry
- `compiler.py`: transforms rules into machine-readable constraints
- `evaluator.py`: evaluates declarative rule expressions against deterministic metrics
- `rationale.py`: generates Markdown rationale from knowledge findings
- `data/bracket_rules.yaml`: initial wall-bracket and L-bracket engineering rules

## Rule Format

Rules are data, not Python logic:

```yaml
rules:
  - id: hole_edge_margin_001
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
```

The evaluator supports a restricted expression language for arithmetic, boolean, and comparison operations. It does not use `eval()` and does not allow function calls, attribute access, imports, or arbitrary Python execution.

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

Generate a design review with knowledge findings:

```bash
python -m intentforge.cli design-review wall_mounted_bracket --knowledge
python -m intentforge.cli design-review l_bracket --knowledge
```

Knowledge-enhanced design review writes:

```text
output/design_review_report.json
output/design_review_summary.md
output/design_knowledge_rationale.md
output/design_review_runs/<run_id>/
```

## Limitations

- Rules are heuristics, not simulation.
- No FEA, load rating, fatigue analysis, or manufacturing-process certification is performed.
- The rule database is intentionally small and deterministic.
- Findings are advisory unless future phases promote specific rules into strict quality gates.
- The current metrics are derived from IntentForge parameter tables and feature flags, not arbitrary imported CAD.
