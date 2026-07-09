# Feature Recognition

IntentForge Phase 18 adds topology-informed feature recognition for generated CadQuery/OpenCascade models.

This is not full industrial CAD feature recognition. It is a conservative layer that checks whether generated geometry appears to contain the expected engineering features for the supported model families.

Supported families:

- `wall_mounted_bracket`
- `l_bracket`

Recognized features:

- through holes
- wall-bracket center cutout
- wall-bracket rounded corners where practical
- L-bracket connected two-leg solid
- L-bracket triangular gusset where practical
- basic solid, face, edge, and validity consistency

Run recognition:

```bash
python -m intentforge.cli recognize-features wall_mounted_bracket
python -m intentforge.cli recognize-features l_bracket
```

Reports are written to:

```text
output/harness/feature_recognition_report.json
output/harness/feature_recognition_summary.txt
output/harness/feature_recognition_runs/<run_id>/
```

Validation reports also include recognition metadata:

```text
validation_report.metadata["feature_recognition"]
```

## Recognition Strategy

The recognizer uses CadQuery/OCC topology where available:

- cylindrical face candidates for through holes
- expected hole axes, diameters, and centers from the parameter table
- internal planar faces for center cutout detection
- solid count and shape validity for L-bracket connected-leg checks
- sloped planar face candidates for triangular gussets

The recognizer is parameter-aware. This avoids confusing optional features with nearby topology, such as rounded outside corners versus through holes.

## Confidence And Warnings

Recognition findings include:

- expected values
- recognized values
- pass/fail result
- confidence: `high`, `medium`, `low`, or `unknown`
- warnings

Low-confidence failures are treated as warnings in Phase 18. This avoids destabilizing the deterministic validation pipeline while still making topology evidence visible to reviewers and harnesses.

## Limits

Current recognition is limited to IntentForge-generated geometry. It does not support arbitrary imported STEP files, freeform CAD, industrial feature trees, or robust fillet reconstruction.
