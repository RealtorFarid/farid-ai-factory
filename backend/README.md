# Propilot AI — backend

The agent runtime and the HTTP API. Python 3.12, FastAPI, PydanticAI.

Run everything from the repository root with `make` (see the
[root README](../README.md)); the commands below are the direct equivalents.

```bash
uv sync --extra dev                      # install
uv run python -m backend.cli             # serve
uv run pytest                            # test
uv run ruff check . && uv run mypy       # lint and type-check
```

## Layout

```
src/backend/
  __init__.py        Version and product name. No import side effects.
  asgi.py            Module-level `app` for `uvicorn backend.asgi:app`.
  cli.py             The `propilot` console script.
  api/
    app.py           Application factory, lifespan, middleware wiring
    deps.py          Dependency injection from app.state
    errors.py        The single error envelope and its handlers
    middleware.py    Request id + access logging
    schemas.py       Request/response models
    routes/
      health.py      Liveness and readiness
      agents.py      List, run, stream
  runtime/
    config.py        Settings (pydantic-settings), validated once
    logger.py        structlog setup; JSON in production
    tracing.py       Optional Langfuse/OTel wiring; no-op without credentials
    agent.py         Agent registry, model resolution, the atlas agent
    runner.py        The one place an agent is actually executed
    events.py        Phase 2 — event bus
    llm.py           Phase 2 — LiteLLM routing
    memory.py        Phase 2 — pgvector memory
    tools.py         Phase 2 — tool registry
    main.py          Smoke script: one real agent turn, no HTTP
    stub.py          Offline model for local verification (PROPILOT_DEFAULT_MODEL=stub)
  db/
    models.py        Schema: tenancy, workspace, claims, consent, runs
    engine.py        Engine and sessions (sync — see D-021)
    seed.py          First-run starter data, idempotent
    repositories/    Postgres implementations of the runtime protocols
migrations/          Alembic; applied as a deploy step, never on boot
```

The Phase 2 modules are documented placeholders, not dead files. The seams are
deliberate: `runner.py` is the only caller of `agent.run()`, so tools, memory
and the approval gate all land in one place.

## Testing

The suite never reaches the network. `pydantic_ai.models.ALLOW_MODEL_REQUESTS`
is disabled globally in `conftest.py`, agents run against `TestModel`, and every
`Settings` is built with `_env_file=None` so results do not depend on the
developer's machine.

```bash
uv run pytest --cov --cov-report=term-missing
```

Coverage is gated at 90%.

Persistence tests need a database and skip without one:

```bash
createdb propilot_test
PROPILOT_TEST_DATABASE_URL=postgresql+psycopg://$(whoami)@localhost:5432/propilot_test \
  uv run pytest tests/test_persistence.py
```

They drop and recreate the schema per test, so never point that variable at a
database you care about.
