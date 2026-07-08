# Benchmark

The benchmark suite is a deterministic regression suite for the current supported model families: `wall_mounted_bracket` and `l_bracket`.

## Categories

Benchmark cases are stored under `benchmark/prompts/`:

- `clean_prompts.json`: prompts that should parse, build, export CAD, and validate
- `default_prompts.json`: prompts with missing details that should use safe defaults and record assumptions
- `optional_feature_prompts.json`: prompts that test requested and omitted optional features
- `hole_pattern_prompts.json`: no-hole, two-hole, four-hole, explicit spacing, and unsupported hole-pattern cases
- `rejection_prompts.json`: unsupported object and vague prompt rejection cases
- `edit_prompts.json`: accepted and rejected natural-language edit cases
- `l_bracket_clean_prompts.json`: clean L-bracket parse-build cases
- `l_bracket_default_prompts.json`: L-bracket prompts that rely on safe defaults
- `l_bracket_optional_feature_prompts.json`: L-bracket omitted/requested feature cases
- `l_bracket_rejection_prompts.json`: unsupported L-bracket prompt cases
- `l_bracket_edit_prompts.json`: accepted and rejected L-bracket edit cases

## Running

```bash
python -m intentforge.cli benchmark
```

The benchmark writes latest reports to:

```text
output/benchmark/benchmark_report.json
output/benchmark/benchmark_summary.txt
```

It also writes a persistent run directory:

```text
output/benchmark/runs/<run_id>/
```

## Report Format

`benchmark_report.json` includes:

- run ID
- total cases
- passed and failed counts
- pass rate
- per-category counts
- per-family counts for `wall_mounted_bracket` and `l_bracket`
- failed case details

`failed_cases.json` and `passed_cases.json` are written in the persistent run directory for focused debugging.
