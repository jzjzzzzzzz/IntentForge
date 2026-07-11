# Product Demo Workflow

The CLI can produce a scoped assurance case after the existing deterministic workflow and package it for downstream review. This adds traceability; it does not expand the two supported CAD families or claim engineering certification.

IntentForge's HTTP API server turns the deterministic CAD pipeline into a
callable backend that external agents, SaaS integrations, or local tools can
use directly.  This document explains the commercial-style demo workflow and
how to run it.

## Starting the API Server

```bash
# Install API dependencies (if not already installed)
python -m pip install "intentforge[api]"

# Start the local server via python -m entry point (reads env vars):
python -m intentforge.api.server

# Environment variables for python -m entry point:
# INTENTFORGE_API_HOST   (default: 127.0.0.1)
# INTENTFORGE_API_PORT   (default: 8765)
# INTENTFORGE_API_TOKEN  (optional Bearer auth token)

# Or via CLI subcommand:
intentforge serve

# With optional token auth:
intentforge serve --token my-secret-token

# Custom host/port:
intentforge serve --host 0.0.0.0 --port 9000
```

Interactive API docs are available at `http://127.0.0.1:8765/docs` (Swagger UI).

## Running the Demo Scripts

Two demo scripts are provided in `examples/`:

```bash
# Minimal API client demo — 5 key endpoint calls
python examples/api_client_demo.py

# Full product workflow demo — 7-step commercial workflow
python examples/product_workflow_demo.py
```

If the API server is not running, both scripts fail with a clear message:

```
❌ Cannot reach IntentForge API.
Start the server:
  python -m intentforge.api.server
```

If token auth is enabled (`INTENTFORGE_API_TOKEN` is set), pass the token:

```bash
python examples/api_client_demo.py --token my-secret-token
python examples/product_workflow_demo.py --token my-secret-token
```

## API Client Demo (api_client_demo.py)

This script makes five sequential calls:

| Step | Endpoint | dry_run | Purpose |
|------|----------|---------|---------|
| 1 | `GET /health` | — | Verify API is reachable |
| 2 | `POST /v1/parse-build` | `true` | Validate intent without STEP/STL export |
| 3 | `POST /v1/parse-build` | `false` | Full CAD generation + validation |
| 4 | `POST /v1/edit-apply` | `true` | Validate edit intent without re-export |
| 5 | `POST /v1/edit-apply` | `false` | Edit + regenerate CAD |

Each step prints: `request_id`, `operation`, `object_type`, `dry_run`,
`validation` summary, `artifacts` list, and `cad_exported`.

### Example Output (Step 2 — dry_run parse-build)

```
  HTTP status   : 200
  ok            : True
  request_id    : req_3f8a1b2c4d5e6f7a
  operation     : parse_build
  object_type   : wall_mounted_bracket
  dry_run       : True
  validation    : valid=True, checks=8, passed=8, failed=0
  cad_exported  : False
```

Notice that `cad_exported` is `False` and no STEP/STL artifact refs appear —
dry-run validates the design intent but does not write CAD files.

### Example Output (Step 3 — full parse-build)

```
  HTTP status   : 200
  ok            : True
  request_id    : req_7b2c3d4e5f6a1b2c
  operation     : parse_build
  object_type   : wall_mounted_bracket
  dry_run       : False
  validation    : valid=True, checks=8, passed=8, failed=0
  artifacts     : 4
    - step → output/.../bracket.step
    - stl  → output/.../bracket.stl
    - intent_json → output/.../intent.json
    - params_yaml → output/.../params.yaml
  cad_exported  : True
```

Now `cad_exported` is `True` and artifact refs include STEP, STL, intent, and
params files.

## Product Workflow Demo (product_workflow_demo.py)

This script runs a 7-step commercial-style workflow:

```
parse → dry-run → build → edit → validate → rejection → artifact list
```

| Step | Endpoint | What it demonstrates |
|------|----------|----------------------|
| 0 | `GET /health` | Connectivity check |
| 1 | `POST /v1/parse` | Parse prompt → intent JSON |
| 2 | `POST /v1/parse-build` (dry) | Validate intent, no export |
| 3 | `POST /v1/parse-build` (full) | Generate STEP/STL + validate |
| 4 | `POST /v1/edit-apply` (dry) | Validate edit, no re-export |
| 5 | `POST /v1/edit-apply` (full) | Regenerate edited CAD |
| 6 | `POST /v1/parse-build` (unsupported) | Clear rejection response |
| 7 | `GET /v1/runs/{kind}/{run_id}` | Retrieve run metadata |

Step 6 intentionally sends an unsupported prompt ("three mounting holes") and
demonstrates that IntentForge returns a structured rejection with `ok: false`,
a `ToolError` with `error_type`, `message`, and `recoverable: true`, and no
CAD artifacts.

## Understanding dry_run

`dry_run` is a critical production safety feature:

- **dry_run=True**: IntentForge parses the prompt, validates intent against
  schemas, checks parameters and constraints, runs the feature plan, and
  validates — but does **not** export STEP/STL files or write persistent
  artifacts.  This lets external agents verify a request before committing to
  CAD generation.

- **dry_run=False**: The full pipeline runs: parse → validate → generate →
  export STEP/STL → validate geometry → write all artifacts.  This is the
  "commit" step after a successful dry-run.

Recommended agent integration pattern:

```text
POST /v1/parse-build  dry_run=True   → check ok, validation
if ok and validation.valid:
    POST /v1/parse-build  dry_run=False  → generate and export CAD
```

## Understanding Artifact Refs

Every successful API response includes an `artifacts` list with `ArtifactRef`
objects:

```json
{
  "artifacts": [
    {"kind": "step",         "path": "output/.../bracket.step",  "description": "STEP export"},
    {"kind": "stl",          "path": "output/.../bracket.stl",   "description": "STL export"},
    {"kind": "intent_json",  "path": "output/.../intent.json",   "description": "Parsed intent"},
    {"kind": "params_yaml",  "path": "output/.../params.yaml",   "description": "Parameter table"}
  ]
}
```

These refs are relative paths under the `output/` directory.  They can be
retrieved via the artifact serving endpoint:

```bash
GET /v1/artifacts/<relative_path>
```

Only paths under `output/` are served.  Path traversal attempts are rejected
with HTTP 403.

## Token Auth

If the environment variable `INTENTFORGE_API_TOKEN` is set, all endpoints
(except `/health`) require:

```
Authorization: Bearer <token>
```

Missing or invalid tokens receive HTTP 401 with a structured error.

Without `INTENTFORGE_API_TOKEN`, auth is disabled and all endpoints are open.

This is suitable for local development and trusted-network deployments.  For
production SaaS, add a proper auth middleware in front of the API server.

## Example API Calls (curl)

```bash
# Health check
curl http://127.0.0.1:8765/health

# Parse a prompt
curl -X POST http://127.0.0.1:8765/v1/parse \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Make a wall-mounted bracket 120mm wide 60mm tall with two screw holes."}'

# Parse-build with dry_run
curl -X POST http://127.0.0.1:8765/v1/parse-build \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Make a wall-mounted bracket 120mm wide 60mm tall with two screw holes.", "dry_run": true}'

# Parse-build (full)
curl -X POST http://127.0.0.1:8765/v1/parse-build \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Make a wall-mounted bracket 120mm wide 60mm tall with two screw holes."}'

# Edit-apply with dry_run
curl -X POST http://127.0.0.1:8765/v1/edit-apply \
  -H "Content-Type: application/json" \
  -d '{"target": "bracket", "edit_text": "Make it 150mm wide but keep the same thickness.", "dry_run": true}'

# Edit-apply (full)
curl -X POST http://127.0.0.1:8765/v1/edit-apply \
  -H "Content-Type: application/json" \
  -d '{"target": "bracket", "edit_text": "Make it 150mm wide but keep the same thickness."}'

# List recent runs
curl http://127.0.0.1:8765/v1/runs/recent?kind=parsed_runs&limit=3

# Get run metadata
curl http://127.0.0.1:8765/v1/runs/parsed_runs/<run_id>

# Retrieve an artifact file
curl http://127.0.0.1:8765/v1/artifacts/output/.../bracket.step

# With auth
curl -H "Authorization: Bearer my-secret-token" \
  http://127.0.0.1:8765/v1/parse-build \
  -d '{"prompt": "..."}'
```

## Response Structure

All endpoints return a contract-compatible `ToolResponse` envelope.  See
[docs/api_contract.md](api_contract.md) for the full specification.

Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `ok` | bool | Whether the operation succeeded |
| `request_id` | string | Unique ID for this request |
| `run_id` | string | Run tracking ID |
| `operation` | string | Which operation was performed |
| `object_type` | string | CAD object type (e.g. `wall_mounted_bracket`) |
| `dry_run` | bool | Whether this was a dry-run |
| `cad_exported` | bool | Whether STEP/STL was actually written |
| `validation` | object | Validation summary (valid, checks, failed) |
| `artifacts` | list | Artifact refs (kind + path) |
| `error` | object | ToolError on failure (error_type, message, recoverable) |
| `warnings` | list | Non-fatal warnings |
| `metadata` | object | Run summary and extra metadata |

## Review-policy CLI

Phase 24 review policies are currently exposed through the Python library and CLI rather than new HTTP endpoints. This keeps the HTTP contract unchanged while review decisions stabilize.

```bash
intentforge assurance build --profile standard --dry-run
intentforge review evaluate output/assurance/assurance_case.json \
  --policy intentforge_standard_design_review_v1
intentforge review provenance output/assurance/review_decision.json --verify
intentforge review diff baseline-review-decision.json candidate-review-decision.json
```

Phase 25 keeps the same interface boundary: provenance replay and multi-variant differential audit are library and CLI operations. No HTTP or MCP contract is expanded, and neither operation generates CAD.

The decision is scoped to the recorded assurance observations. It is not regulatory approval or production authorization.
