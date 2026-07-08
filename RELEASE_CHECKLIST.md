# Release Checklist

Use this checklist before tagging or sharing a release.

- `python -m pytest` passes
- `python -m intentforge.cli benchmark` passes
- CLI smoke tests pass:
  - `python -m intentforge.cli parse-build "Make a wall-mounted bracket 120 mm wide, 60 mm tall, 8 mm thick, with two screw holes."`
  - `python -m intentforge.cli edit-parse-apply bracket "Change it to four mounting holes."`
  - `python -m intentforge.cli edit-parse-apply bracket "Change it to three mounting holes."`
- `python -m intentforge.cli demo` runs and writes `demo_report.json`
- README is current
- docs are current
- `PROJECT_STATUS.md` is current
- optional MCP dependency remains optional
- CadQuery optional behavior still works for non-CAD parser/tests
- CadQuery-enabled CAD exports are real STEP/STL files
- rejected edits do not export new edited CAD
- no stale generated outputs are committed unless intentionally included
- benchmark reports and demo reports are traceable to run IDs

