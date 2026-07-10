# Engineering Reasoning Engine

Phase 20.6 adds a deterministic engineering reasoning layer on top of the engineering knowledge system.

The reasoning engine connects evaluated knowledge findings into traceable explanations. It does not generate CAD, edit geometry, run FEA, call an LLM, or claim safety certification.

## Purpose

The knowledge layer can report that a rule passed or failed. The reasoning layer explains how findings relate:

```text
knowledge findings
-> rule interactions
-> trade-offs
-> conflicts
-> priorities
-> recommendations
-> EngineeringReasoningReport
```

This helps a reviewer understand why one recommendation may affect another part of the design.

## Architecture

Implementation lives under `src/intentforge/knowledge/reasoning/`:

- `schema.py`: stable Pydantic schemas and deterministic ID helpers
- `interactions.py`: metadata-backed rule interaction detection
- `tradeoffs.py`: benefit/cost statements from rule metadata
- `conflicts.py`: advisory conflict detection
- `priorities.py`: deterministic priority scoring
- `recommendations.py`: recommendation generation and duplicate merging
- `engine.py`: report orchestration
- `templates.py`: Markdown rendering
- `benchmark.py`: focused reasoning benchmark
- `verification.py`: golden-case verification, contradiction checks, and applicability checks
- `data/golden_cases.yaml`: reproducible engineering cases with expected reasoning outputs

The reasoning package is independent from CadQuery. It consumes knowledge rules, knowledge findings, optional metrics dictionaries, and feature-recognition metadata.

## Determinism

The same inputs should produce the same structured reasoning result:

- model family
- knowledge findings
- rule IDs
- rule versions
- reasoning metadata
- reasoning engine version
- optional metrics

`EngineeringReasoningReport.report_id` is deterministic and excludes timestamps and local file paths.

Phase 20.7 adds golden engineering cases. Each case records expected triggered rules, expected interactions, expected conflicts, expected recommendation priorities, and expected deterministic report ID. This makes reasoning regressions explicit rather than relying only on broad test coverage.

Rule version and reasoning engine version are separate:

```text
Rule version: hole_edge_margin_001 v1.0
Reasoning engine version: 1.0
```

## Supported Reasoning

Initial reasoning support includes:

- reinforcing findings
- conflicting rule recommendations
- dependency relationships
- mitigation relationships
- engineering trade-offs
- deterministic priority scoring
- advisory recommendations

Supported interaction types:

- `reinforces`
- `conflicts`
- `depends_on`
- `affects`
- `duplicates`
- `mitigates`

Supported conflict types:

- `parameter_conflict`
- `recommendation_conflict`
- `priority_conflict`
- `geometry_constraint_conflict`

Supported priorities:

- `critical`
- `high`
- `medium`
- `low`
- `informational`

## Priority Model

Priority is scored deterministically from:

- finding severity
- finding confidence
- rule `priority_weight`
- reinforcing interactions
- conflict participation
- mitigation relationships

The model is heuristic. A high-priority recommendation means the deterministic rule system found a more important advisory issue. It does not mean the design is certified unsafe.

## CLI Usage

Show reasoning engine capabilities:

```bash
python -m intentforge.cli knowledge reasoning-info
```

Validate reasoning metadata:

```bash
python -m intentforge.cli knowledge reasoning-validate
```

Run golden-case reasoning verification:

```bash
python -m intentforge.cli knowledge reasoning-verify
```

Run the standalone reasoning benchmark:

```bash
python -m intentforge.cli knowledge reasoning-benchmark
```

Generate a design review with knowledge and reasoning:

```bash
python -m intentforge.cli design-review wall_mounted_bracket --knowledge --reasoning
python -m intentforge.cli design-review l_bracket --knowledge --reasoning
```

Write standalone JSON knowledge and reasoning reports:

```bash
python -m intentforge.cli design-review wall_mounted_bracket --knowledge --reasoning --json
```

Reasoning outputs include:

```text
output/engineering_reasoning_report.md
output/engineering_reasoning_report.json
output/design_review_runs/<run_id>/
output/harness/reasoning_verification_report.json
output/harness/reasoning_benchmark_report.json
```

## Verification Checks

Golden verification checks:

- expected deterministic report IDs
- stable repeated report generation
- expected interaction types
- expected conflict counts
- expected recommendation priorities
- expected recommendation text keys
- direct recommendation contradictions
- recommendation applicability to supported family rules and declared parameters

Contradiction detection is intentionally conservative. It only flags direct opposite actions over the same explicitly mentioned affected parameter.

## Example: Wall Bracket

If hole edge margin and hole spacing warnings are both active, the reasoning engine can report:

- the findings conflict within a fixed plate envelope
- increasing one spacing dimension may worsen the other
- increasing plate width should be considered before reducing hole spacing

This is advisory and must still be validated after any edit.

## Example: L-Bracket

If a tall thin L-bracket triggers the gusset recommendation, the reasoning engine can report:

- adding a gusset may improve support near the inside corner
- the trade-off is added material, weight, and manufacturing complexity
- the recommendation is heuristic and not a stiffness simulation

## Limitations

- No FEA.
- No load certification.
- No automated safety approval.
- No professional engineering replacement.
- Only `wall_mounted_bracket` and `l_bracket` are supported.
- Reasoning quality depends on encoded rule quality.
- Recommendations remain advisory.
- Unsupported engineering domains must be rejected or left unknown.
- Golden cases verify deterministic behavior for encoded scenarios; they are not proof of structural safety.
