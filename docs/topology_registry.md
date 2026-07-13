# Declarative Topology Registry

Phase 32 makes CAD family metadata modular while keeping execution closed and
deterministic.

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
intentforge topology build-json flange-intent.json --output-root output
```

Unknown families produce a structured `safe_rejection` envelope with
`cad_exported: false`. The envelope has a SHA-256 content address for
integrity. It is explicitly marked as not cryptographically signed because
IntentForge does not manage identity keys.

## Compatibility

The two bracket families use registry manifests that point to their established
parser, geometry, and validator adapters. Existing rule IDs, evidence IDs,
capability counts, benchmark cases, artifacts, APIs, and audit contracts remain
unchanged.
