# Design Review Reports

IntentForge design review reports summarize why a generated CAD result should be trusted for the supported deterministic workflows.

Generate a report:

```bash
python -m intentforge.cli design-review wall_mounted_bracket
python -m intentforge.cli design-review l_bracket
```

Outputs:

```text
output/design_review_report.json
output/design_review_summary.md
output/design_review_runs/<run_id>/
```

## Contents

Each design review report includes:

- original request and objective when available
- supported model family
- named parameters with values, units, sources, and reasons
- active and omitted features
- feature plan steps
- validation summary and warnings
- topology metrics
- volume delta checks
- feature recognition results
- generated or planned artifacts
- current limitations

The Markdown summary is intended for quick human review. The JSON report is intended for agents, APIs, and test harnesses.

## Trust Model

Design review reports do not replace engineering sign-off. They collect the evidence IntentForge has:

- deterministic intent extraction or guarded LLM translation
- named parameter tables
- feature flags and feature plans
- geometry validation
- topology inspection
- volume delta checks
- feature recognition

Remaining warnings are kept visible so the user can distinguish verified behavior from assumptions and current limitations.

## Limits

Reports are only generated for the supported model families:

- `wall_mounted_bracket`
- `l_bracket`

They do not claim arbitrary CAD support, material analysis, load analysis, tolerance analysis, or manufacturing validation.
