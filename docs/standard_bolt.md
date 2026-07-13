# Standard Bolt Topology

`standard_bolt` is a registry-native deterministic fastener macro-model.

## Parameters

- `nominal_diameter`
- `thread_pitch`
- `shank_length`
- `thread_length`
- `head_type`: `hexagonal` or `socket_cap`

The manifest derives total body length and a metric tensile stress-area
approximation through the same closed arithmetic AST used for remediation.
The CadQuery builder creates the shank, thread major-diameter envelope, and
selected head. Detailed helical thread flanks are intentionally omitted for
predictable performance and are disclosed in validation metadata.

This topology does not certify a dimensional standard, tolerance class,
material, strength grade, torque, preload, fatigue life, or service suitability.
