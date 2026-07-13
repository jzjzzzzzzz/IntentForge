# Industrial Flange Foundation

`industrial_flange` is the first registry-native component family.

## Parameters

- `flange_outer_diameter`
- `bolt_circle_diameter`
- `bolt_hole_diameter`
- `hole_count`
- `flange_thickness`
- `bore_diameter`

The geometry factory builds one flat cylindrical ring, cuts the central bore,
and cuts an equally spaced polar bolt-hole pattern. It exports through the
existing STEP/STL workflow and uses the existing validation, assurance, CAS,
and release-dossier infrastructure.

## Engineering Metric Binding

The manifest computes hole edge distance as:

```text
(flange_outer_diameter - bolt_circle_diameter) / 2
- bolt_hole_diameter / 2
```

That mapping feeds deterministic knowledge evaluation and allows the Phase 30
remediation solver to adjust `flange_outer_diameter` to a rule boundary.

## Limitations

This is an ASME B16.5-oriented modeling foundation, not an ASME B16.5
conformance implementation. It does not select or certify pressure class,
material, facing, hub, neck, gasket, bolting, tolerances, loads, temperature,
manufacturing process, or service suitability. The current geometry is a flat
ring flange and requires external engineering review for real service use.
