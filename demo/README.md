# IntentForge Demo

Run the release demo with:

```bash
python -m intentforge.cli demo
```

or:

```bash
python demo/run_demo.py
```

The demo runs:

- two-hole bracket parse-build
- four-hole bracket with center cutout parse-build
- accepted width edit that preserves thickness
- accepted four-hole edit
- intentionally rejected vague edit
- full deterministic benchmark

Outputs are written under:

```text
output/demo_runs/<run_id>/
```

Each run writes `demo_report.json` and `demo_summary.txt`.

