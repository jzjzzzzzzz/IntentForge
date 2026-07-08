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

Bounding-box checks use the generated CadQuery model. Hole, cutout, and L-bracket per-leg hole checks are parameter-based in this phase.

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

IntentForge does not yet perform robust topological detection of holes, cutouts, or fillets directly from the solid. It validates those features from the parameter table, feature flags, and feature plan. This is intentional for the current phase because unreliable geometry recognition would create false confidence.

For L-brackets, inside fillet intent is represented in parameters and validation, but robust geometric inside-corner filleting is future work.
