# Spur Gear Topology

`spur_gear` is a registry-native deterministic transmission component.

## Parameters

- `module`
- `teeth_count`
- `pressure_angle`
- `face_width`
- `bore_diameter`

The manifest derives pitch-circle diameter as `module * teeth_count` and the
full-depth root-circle approximation as `(teeth_count - 2.5) * module`. Bore
material margin is evaluated through the closed arithmetic AST and can be
inverted deterministically within declared parameter bounds.

The CadQuery builder samples a bounded transverse involute approximation and
extrudes it to the requested face width. It does not model profile shift,
backlash, undercut correction, tip relief, contact stress, efficiency, wear, or
noise. It is not an ISO gear accuracy or service certification.
