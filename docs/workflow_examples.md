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

## L-Bracket

```bash
python -m intentforge.cli parse-build "Make an L-bracket 100 mm base leg, 80 mm vertical leg, 40 mm wide, and 6 mm thick."
```

Expected behavior:

- object type: `l_bracket`
- active features: `base_leg`, `vertical_leg`
- no holes unless requested
- STEP/STL exported as `parsed_l_bracket.step` and `parsed_l_bracket.stl`
- validation checks bounding box against base leg, vertical leg, and width

## L-Bracket With Holes

```bash
python -m intentforge.cli parse-build "Make an L-bracket with two holes on the base and two holes on the vertical face."
```

Expected behavior:

- active features: `base_leg`, `vertical_leg`, `base_mounting_holes`, `vertical_mounting_holes`
- only two holes per leg are supported
- hole validation is parameter-based; no topological hole detection yet

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

## Accepted L-Bracket Edit

```bash
python -m intentforge.cli edit-parse-apply l_bracket "Make the base leg 120 mm long."
```

Expected behavior:

- base leg length changes
- vertical leg, width, thickness, holes, and feature flags are preserved unless explicitly edited
- edited L-bracket STEP/STL exports are written

## Rejected Edit

```bash
python -m intentforge.cli edit-parse-apply bracket "Change it to three mounting holes."
```

Expected behavior:

- edit is rejected
- no new edited CAD is exported
- edit report explains that only two-hole and four-hole patterns are supported
