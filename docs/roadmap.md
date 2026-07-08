# Roadmap

IntentForge should expand only when the intent pipeline remains explicit, testable, and validated.

## Phase 10

Add a second model family while preserving the same core flow:

```text
prompt -> intent -> parameters -> constraints -> feature plan -> CAD -> validation -> edits
```

The next model family should be small enough to keep deterministic behavior and meaningful tests.

## Candidate Families

`L-bracket` is the likely next family. It adds a second plate face and bend/leg relationships while still staying close to the current bracket domain.

`electronics enclosure` is a later candidate. It would require stronger support for shells, lids, bosses, openings, clearances, and assembly intent.

## Future Capabilities

- topological feature detection for generated solids
- stronger constraint solving
- actual LLM-assisted parsing that emits the existing schemas
- richer edit intent handling
- GUI after the backend is stable
- CAD plugin integration after the backend can be trusted independently

## Non-Goals For The Current Phase

- arbitrary CAD generation
- freeform feature placement
- desktop CAD automation
- replacing the deterministic parser with an LLM

