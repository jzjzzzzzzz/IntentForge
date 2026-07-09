# Development

IntentForge uses a `src/` layout for importable Python packages and supports `uv` for local development.

PyPI users should still install with pip:

```bash
pip install intentforge
pip install "intentforge[api]"
pip install "intentforge[cad]"
```

## Source Layout

Importable packages live under `src/`:

- `src/intentforge/`
- `src/mcp_server/`
- `src/benchmark/`
- `src/harness/`

Repo assets stay at the project root:

- `tests/`
- `docs/`
- `examples/`
- `demo/`
- `output/.gitkeep`

The `src/` layout prevents tests from accidentally importing packages from the repository root instead of the installed package.

## uv Workflow

Install uv from the official project instructions if it is not already available.

Common commands:

```bash
uv sync
uv sync --extra api
uv sync --extra cad
uv sync --all-extras
uv run pytest
uv run intentforge doctor
uv run intentforge benchmark
uv run intentforge technical-harness --quick
uv run intentforge demo
```

CadQuery-dependent commands require the `cad` extra. FastAPI API server work requires the `api` extra.

## pip Workflow

Editable install for local development:

```bash
python -m pip install -e ".[dev]"
```

Install all optional developer extras:

```bash
python -m pip install -e ".[dev,api,cad,mcp,client]"
```

Run tests:

```bash
python -m pytest
```

## Build Checks

Before packaging work:

```bash
rm -rf dist build *.egg-info src/*.egg-info
python -m build
python -m twine check dist/*
```

Inspect built archives:

```bash
python -m zipfile -l dist/intentforge-*.whl | head -160
tar -tzf dist/intentforge-*.tar.gz | head -160
```

The wheel should contain importable packages as `intentforge/`, `mcp_server/`, `benchmark/`, and `harness/`, plus runtime JSON/YAML package data for benchmark and harness tools. It should not contain generated `output/` artifacts, `.claude/`, or `CLAUDE.md`.
