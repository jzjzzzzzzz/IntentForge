# Agent Instructions

IntentForge is an intent-preserving CAD project. The first supported model family is `wall_mounted_bracket`.

## Current Phase

Implement only simple, testable Python components for the MVP. Do not add LLM calls, GUI automation, SolidWorks/Fusion/FreeCAD control, broad CAD object support, or MCP behavior until those phases are explicitly requested.

## Engineering Rules

- Use named parameters for important dimensions.
- Preserve assumptions, unknowns, constraints, feature reasons, and validation checks.
- Keep model-family behavior explicit. Do not silently generalize beyond `wall_mounted_bracket`.
- Prefer deterministic validation and small data models over clever parsing.
- Add pytest coverage for behavior that could break design intent.
- Fix implementation causes when tests fail. Do not weaken tests to hide failures.

## CAD Rules

Future CadQuery generation should create editable parametric models from a feature plan, not one-off visual approximations. Feature steps should map to meaningful construction operations and each step must have a reason.
