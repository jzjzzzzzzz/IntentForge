# Workflow Examples

These examples use the deterministic CLI. CadQuery is required for commands that export STEP/STL files.

## Two-Hole Bracket

```bash
python -m intentforge.cli parse-build "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes."
```

Expected behavior:

- object type: `wall_mounted_bracket`
- active features: `mounting_holes`
- hole pattern: `symmetric_2_horizontal`
- center cutout omitted
- STEP/STL exported
- validation report written

## Four-Hole Bracket With Cutout

```bash
python -m intentforge.cli parse-build "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with four corner screw holes and a center cutout."
```

Expected behavior:

- active features: `mounting_holes`, `center_cutout`
- hole pattern: `rectangular_4`
- default cutout size recorded as assumptions when not specified
- STEP/STL exported
- validation report written

## Plain Mounting Plate

```bash
python -m intentforge.cli parse-build "Make a plain mounting plate 100 mm wide, 50 mm tall, and 6 mm thick."
```

Expected behavior:

- no mounting holes
- no center cutout
- no rounded corners unless requested
- STEP/STL exported
- validation ignores omitted optional features

## Accepted Edit

```bash
python -m intentforge.cli edit-parse-apply bracket "Make it 150 mm wide but keep the same thickness."
```

Expected behavior:

- width changes
- thickness is preserved
- unchanged parameters and feature flags remain in place
- edited STEP/STL exports are written
- edited validation report is written

## Rejected Edit

```bash
python -m intentforge.cli edit-parse-apply bracket "Change it to three mounting holes."
```

Expected behavior:

- edit is rejected
- no new edited CAD is exported
- edit report explains that only two-hole and four-hole patterns are supported

