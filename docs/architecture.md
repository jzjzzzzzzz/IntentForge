# Architecture

IntentForge is organized as a deterministic CAD intent pipeline. Each module owns one part of the path from prompt to validated CAD.

## Core Modules

`intentforge.schemas` defines Pydantic models for intent, parameters, constraints, feature plans, validation reports, and edit reports. These schemas are the contract between pipeline stages.

`intentforge.parser` contains deterministic regex-based parsers for initial CAD prompts and natural-language edit requests. The parser supports wall-mounted bracket / mounting-plate requests and the Phase 10 L-bracket family.

`intentforge.features` normalizes family-aware feature flags. Wall-bracket flags cover mounting holes, center cutouts, rounded corners, and edge fillets. L-bracket flags cover base and vertical legs, per-leg holes, inside/outside fillets, and the optional triangular gusset.

`intentforge.planner` creates feature history plans from active feature flags. The plan records which features are built, in which order, and why.

`intentforge.generator` builds CadQuery geometry from the parameter table and feature flags. It reads important dimensions from named parameters rather than hard-coded CAD dimensions. Family dispatch currently routes to `build_wall_bracket` or `build_l_bracket`.

`intentforge.validator` checks geometry and intent. Geometry checks are parameter and bounding-box driven. Intent checks verify object type, required parameters, feature ordering, and pattern consistency.

`intentforge.editor` applies structured edits to an existing parameter table and feature state. It preserves unchanged parameters and rejects unsupported or invalid edits before CAD export.

`intentforge.workflows` contains shared orchestration used by both the CLI and MCP wrapper. This keeps command-line and agent-tool behavior aligned.

`mcp_server` exposes a thin optional MCP wrapper around the workflow functions. It does not duplicate parser, generator, validator, or editor logic.

`benchmark` contains deterministic regression cases and a runner that exercises parsing, CAD generation, validation, edits, rejection behavior, and traceability.

## Output Flow

Commands write latest convenience outputs and persistent run directories. Persistent directories include prompt text, structured artifacts, run metadata, CAD exports where applicable, and validation or edit reports.
