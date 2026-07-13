# Declarative Topology Registry

Phase 32 made CAD family metadata modular. Phase 33 proves horizontal registry
expansion with transmission and fastener components while keeping execution
closed and deterministic.

## Manifest Contract

Each packaged manifest declares:

- a stable topology family and manifest version
- aliases used for deterministic family detection
- controlled parameter types, defaults, units, and conservative safe bounds
- supported features and their parameter dependencies
- closed parser, geometry-factory, and validator adapter IDs
- immutable evidence-catalog and active-rule references
- safe arithmetic mappings from family parameters to engineering metrics
- limitations and scope notes

The registry sorts families by stable ID and rejects duplicate aliases,
unknown adapters, malformed bounds, unknown expression variables, and
unsupported status values.

## Execution Boundary

YAML cannot execute code. It cannot dynamically import a module, select an
arbitrary callable, run a shell command, or invoke an LLM. Runtime adapters are
compiled into closed Python mappings. Formula evaluation uses a restricted
arithmetic AST and never uses `eval()` or `exec()`.

## Commands

```bash
intentforge topology list
intentforge topology validate
intentforge topology schema industrial_flange
intentforge topology schema spur_gear
intentforge topology schema standard_bolt
intentforge topology build-json flange-intent.json --output-root output
```

Unknown families produce a structured `safe_rejection` envelope with
`cad_exported: false`. The envelope has a SHA-256 content address for
integrity. It is explicitly marked as not cryptographically signed because
IntentForge does not manage identity keys.

## Compatibility

The two bracket families use registry manifests that point to their established
adapters. Registry-native adapters cover `industrial_flange`, `spur_gear`, and
`standard_bolt`. The gear exposes pitch/root circle formulas and bore margin;
the bolt exposes total-length and tensile stress-area approximations through the
same closed arithmetic grammar. Existing rule IDs, evidence IDs, capability
counts, benchmark cases, artifacts, APIs, and audit contracts remain unchanged.
