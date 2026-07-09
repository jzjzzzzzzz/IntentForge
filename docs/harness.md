# Harness

IntentForge includes three deterministic harness layers that are useful for regression and release work.

## Edit Preservation Harness

The edit preservation harness checks whether IntentForge can modify an existing model while preserving the design intent that was already established.

It exercises:

- structured and natural-language edits
- parameter preservation
- optional feature state consistency
- validation after edits
- topology inspection when available
- volume delta checks when relevant
- rejection behavior without CAD export

Run it with:

```bash
python -m intentforge.cli edit-harness
```

Reports are written to:

```text
output/harness/edit_preservation_report.json
output/harness/edit_preservation_summary.txt
output/harness/edit_preservation_runs/<run_id>/
```

## Adversarial Rejection Harness

The adversarial rejection harness checks whether unsupported and unsafe requests are rejected instead of being silently converted into a supported bracket.

It covers unsupported objects, unsupported geometry, vague optimization requests, invalid dimensions, unsupported hole counts, and mixed prompts such as a gear-shaped wall bracket or drone frame mounting plate.

Run it with:

```bash
python -m intentforge.cli adversarial-harness
```

Reports are written to:

```text
output/harness/adversarial_report.json
output/harness/adversarial_summary.txt
output/harness/adversarial_runs/<run_id>/
```

Rejected cases pass only when the rejection includes a clear error message and no STEP/STL files are exported.

## Sweep Harness

The sweep harness stresses valid and invalid parameter combinations for both supported families.

Run it with:

```bash
python -m intentforge.cli sweep --max-cases-per-family 30
```

## Topology and Volume Harnesses

IntentForge also includes topology inspection and volume delta checks to support future topology-aware validation work.

These are intentionally parameter- and intent-driven today. They do not replace the existing validation pipeline.
