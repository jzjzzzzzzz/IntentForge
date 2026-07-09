# Validation

IntentForge validates both geometry and design intent.

## Geometry Validation

Geometry validation checks the generated CadQuery model against the parameter table. Current checks include:

- positive parameter ranges
- bounding-box width, height, and thickness
- L-bracket bounding-box base leg, vertical leg, and bracket width
- mounting-hole spacing limits
- mounting-hole diameter limits
- L-bracket base and vertical hole spacing limits
- L-bracket gusset dimension limits when active
- center cutout inside plate limits
- corner radius limits
- edge fillet radius limits
- exported STEP/STL file existence and size
- topology metrics in validation metadata when CadQuery inspection is available
- feature recognition metadata for supported generated features

Bounding-box checks use the generated CadQuery model. Hole, cutout, and L-bracket per-leg hole sizing checks remain parameter-based, with topology-informed feature recognition recorded separately in report metadata.

## Feature Recognition Metadata

Phase 18 adds topology-informed feature recognition to geometry validation metadata:

```text
validation_report.metadata["feature_recognition"]
```

The recognizer inspects CadQuery/OpenCascade topology where available:

- cylindrical face candidates for through holes
- internal planar faces near the center cutout
- solid count and validity for connected L-bracket legs
- sloped planar faces for triangular gussets where practical
- basic face, edge, and solid topology consistency

Feature recognition is conservative. If the recognizer is not confident, it records structured warnings instead of pretending success. Ordinary validation does not crash when recognition cannot be completed.

## Intent Validation

Intent validation checks whether the structured design state is internally consistent. It verifies:

- object type is `wall_mounted_bracket`
- object type is `l_bracket` for L-bracket prompts
- required parameters exist
- required constraints exist
- active feature plan steps exist
- mounting-hole pattern matches hole count
- L-bracket hole counts are 0 or 2 per leg
- L-bracket legs are created and joined before cuts, gussets, or fillets
- base plate is created before cuts
- requested center cutout appears in the feature plan

## Current Limits

IntentForge does not yet perform full industrial CAD feature recognition from arbitrary solids. Phase 18 recognition is topology-informed, parameter-aware, and limited to generated `wall_mounted_bracket` and `l_bracket` models.

For L-brackets, inside fillet intent is represented in parameters and validation, but robust geometric inside-corner filleting is future work.
