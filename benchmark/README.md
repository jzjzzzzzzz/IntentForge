# IntentForge Benchmark Suite

This directory contains a deterministic regression suite for IntentForge.
It exercises parsing, CAD generation, validation, edit handling, rejection
behavior, and output traceability for the supported `wall_mounted_bracket`
pipeline.

Run the benchmark from the repository root:

```bash
python -m intentforge.cli benchmark
```

The benchmark runner loads prompt sets from `benchmark/prompts/`, compares
actual workflow results against the expected outcomes, and writes summary
artifacts under `output/benchmark/`.

The benchmark is intentionally limited to the existing rule-based workflows.
It does not use an LLM and does not expand support beyond the bracket family.
