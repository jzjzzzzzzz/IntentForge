# Design Intent

Design intent in IntentForge means the model keeps a structured explanation of what it is, which parameters drive it, which features are active, and what should be preserved during edits.

## Parameters

Important dimensions are named parameters such as `back_plate_width_mm`, `back_plate_height_mm`, `back_plate_thickness_mm`, `mounting_hole_diameter_mm`, and `mounting_hole_spacing_mm`. Reports and edit handling use canonical parameter names internally.

## Assumptions And Unknowns

The parser records assumptions when values are defaulted or inferred. Examples include default units, default plate dimensions, default hole diameter, and derived hole spacing.

Unknowns record missing engineering context such as material, load requirement, screw standard, manufacturing method, and tolerance requirement.

## Optional Features

Optional features are explicit flags:

- `mounting_holes`
- `center_cutout`
- `rounded_corners`
- `edge_fillets`

Each feature is `requested_by_user`, `defaulted_by_system`, or `omitted`. The generator only builds active features.

## Feature Plans

Feature plans describe construction order. The base plate is created first. Active cuts and finishing features are added afterward with reasons and validation references.

## Validation

Validation checks whether the generated model and structured intent agree with the parameter table and constraints. Validation is part of the pipeline, not a separate manual step.

## Edit Preservation

An edit request modifies the existing parameter table and feature flags. Unchanged parameters are preserved. Unsupported edits, invalid dimensions, and unsupported hole counts are rejected before new edited CAD is exported.

