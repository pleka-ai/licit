## Git
- Conventional Commits. `git add -p`. Commit after every discrete unit.
- One branch per task: `<type>/<desc>`. Branch from `origin/main`.
- Never stash. Use `wip:` commits instead.

## Code
- Python 3.12+, strict `mypy`, Ruff (line 88), Google docstrings.
- `uv add <pkg>` for deps — never edit pyproject.toml directly.
- NEVER lint manually. On ruff failures run `uv run task lint` first.
- No hardcoded values — `shared/config.py` is the source of truth.

## Imports
- `from shared.{models,enums,config,db,codice,logger} import ...`
- `from etl.{parsers,repositories,services,handlers} import ...`
- `from export import {raw,compact,modelo,d1,derived}`

## Naming
- API routes and response fields (worker/), warehouse tables and columns: **Spanish** (PLACSP terminology).
- Python internals (vars, functions, docstrings): **English**.

## Data model
- `schema/` is the parser's staging (CODICE). The public model is `warehouse/` (SQLMesh, Kimball): see `warehouse/README.md`.
- No `dim_`/`fact_` prefixes: the role is a model tag and its description.
- `uv run sqlmesh -p warehouse test` for model unit tests.

## Testing
- `uv run pytest tests/` before committing.
- ETL smoke test: `PYTHONPATH=src uv run python -m etl.handlers.feed_reader --help`

## Deploy
- GitHub Actions (etl.yml, historico.yml) + Cloudflare (Worker, D1, R2). See README.
- This repository is public on GitHub, take that into consideration
- Make sure the actions pass. All tests must pass before pushing to remote.
- Fix everything, even if you dont made the errors. 
