# API Contract

Phase 13 hardens the external tool interface for CLI, MCP, agent, and future service integrations. It does not add CAD features or create a release tag.

## Response Envelope

Successful tool responses include a common envelope:

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "run_id": "20260709_120000_example",
  "object_type": "wall_mounted_bracket",
  "operation": "parse_build",
  "artifacts": [],
  "validation": {},
  "quality_gates": null,
  "warnings": [],
  "metadata": {}
}
```

The legacy workflow keys such as `latest_outputs`, `persistent_outputs`, `validation_valid`, and `edit_report` remain available for compatibility.

## Error Envelope

Rejected or failed requests return `ok: false` with a structured error object:

```json
{
  "ok": false,
  "request_id": "req_abc123",
  "operation": "parse_build",
  "error": {
    "error_type": "UnsupportedObjectError",
    "message": "Unsupported object type for this phase.",
    "recoverable": true,
    "suggested_action": "Use one of the supported model families: wall_mounted_bracket or l_bracket."
  },
  "cad_exported": false,
  "artifacts": [],
  "warnings": []
}
```

Rejected prompts and edits are treated as recoverable tool responses, not crashes.

## Error Types

Standard public error types are:

- `UnsupportedObjectError`
- `UnsupportedGeometryError`
- `InvalidParameterError`
- `ValidationFailedError`
- `CadBackendUnavailableError`
- `CadGenerationError`
- `EditRejectedError`
- `AmbiguousRequestError`
- `ArtifactError`
- `LLMProviderUnavailableError`
- `InternalError`

The implementation may preserve older compatibility keys such as `error_type` and `message` at the top level.

## Artifact References

Artifacts are reported with a normalized reference format:

```json
{
  "kind": "step",
  "path": "output/parsed_bracket.step",
  "persistent": false,
  "object_type": "wall_mounted_bracket",
  "exists": true,
  "generated": true,
  "metadata": {}
}
```

Supported artifact kinds are:

- `intent_json`
- `params_yaml`
- `feature_plan_json`
- `validation_report`
- `edit_report`
- `step`
- `stl`
- `benchmark_report`
- `harness_report`
- `summary_text`

Dry-run STEP/STL references may be marked as planned with `generated: false` and `metadata.planned: true`.

## Dry Run

Dry-run parse-build:

```bash
python -m intentforge.cli parse-build "Make a wall-mounted bracket 120 mm wide, 60 mm tall, with two screw holes." --dry-run
```

Dry-run edit:

```bash
python -m intentforge.cli edit-parse-apply bracket "Make it 150 mm wide but keep the same thickness." --dry-run
```

Dry-run behavior:

- parses the prompt or edit
- builds and validates feasibility in memory when CadQuery is available
- writes structured non-CAD reports where useful
- does not export STEP/STL files
- returns `dry_run: true`
- returns `cad_exported: false`

LLM parse-build and LLM edit-apply commands also support dry-run. In those paths, the LLM translation and schema guard run first, then the deterministic core checks feasibility without exporting CAD.

## LLM Translator Responses

Optional LLM commands use the same response envelope:

- `llm_parse`
- `llm_parse_build`
- `llm_edit_parse`
- `llm_edit_apply`

If no provider is configured, they return:

```json
{
  "ok": false,
  "operation": "llm_parse",
  "error": {
    "error_type": "LLMProviderUnavailableError",
    "message": "No LLM provider is configured.",
    "recoverable": true
  },
  "cad_exported": false
}
```

The LLM never generates CadQuery code or CAD geometry. It only returns structured JSON that must pass schema guardrails before deterministic workflows run.

## Example Parse-Build Response

```json
{
  "ok": true,
  "request_id": "req_abc123",
  "run_id": "20260709_120000_wall_bracket",
  "object_type": "wall_mounted_bracket",
  "operation": "parse_build",
  "validation_valid": true,
  "cad_exported": true,
  "artifacts": [
    {
      "kind": "step",
      "path": "output/parsed_bracket.step",
      "persistent": false,
      "object_type": "wall_mounted_bracket"
    }
  ],
  "validation": {
    "valid": true,
    "failed_checks": 0
  },
  "warnings": []
}
```

## Example Rejected Edit Response

```json
{
  "ok": false,
  "accepted": false,
  "request_id": "req_abc123",
  "operation": "edit_parse_apply",
  "object_type": "wall_mounted_bracket",
  "cad_exported": false,
  "artifacts": [],
  "error": {
    "error_type": "AmbiguousRequestError",
    "message": "Edit request is ambiguous or not measurable.",
    "recoverable": true
  }
}
```

## MCP Compatibility

MCP tool functions call the same shared workflows as the CLI. Their responses include the same contract fields:

- `ok`
- `request_id`
- `operation`
- `object_type` where relevant
- `artifacts`
- `validation`
- `error` on failure

The MCP wrapper does not duplicate parser, generator, validator, editor, or LLM translator logic.
