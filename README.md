# Propilot AI

An AI operating system for real-estate professionals.

This repository holds the agent runtime and the HTTP API in front of it.

**Status:** Phase 1 complete — a production-shaped FastAPI service running a
single agent (`atlas`), with configuration, structured logging, optional
tracing, containerisation and CI. Tools, memory, multi-agent orchestration and
the human-in-the-loop approval gate are Phase 2. See [docs/ROADMAP.md](docs/ROADMAP.md).

---

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv will fetch it).

```bash
git clone https://github.com/RealtorFarid/farid-ai-factory.git
cd farid-ai-factory

cp backend/.env.example backend/.env    # then add your OpenAI key
make install
make run
```

The API is then on <http://127.0.0.1:8000>, with docs at `/docs`.

```bash
curl localhost:8000/health
curl localhost:8000/v1/agents

curl -X POST localhost:8000/v1/agents/atlas/run \
  -H 'content-type: application/json' \
  -d '{"prompt": "Draft a 30-day marketing plan for a new condo listing."}'
```

Or with Docker:

```bash
docker compose up --build
```

---

## Common tasks

| Command | What it does |
|---|---|
| `make install` | Create the venv, install all dependencies |
| `make run` | Start the API server |
| `make test` | Run the test suite |
| `make cov` | Test suite with a coverage report (gate: 90%) |
| `make check` | Everything CI runs: lint, format, mypy, coverage |
| `make format` | Apply formatting and safe lint fixes |
| `make smoke` | One agent turn against a real model (needs credentials) |
| `make docker-up` | Build and start the container stack |

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness. Dependency-free, always 200 when the process is up. |
| `GET` | `/health/ready` | Readiness: agents registered, credentials present, tracing state. |
| `GET` | `/v1/agents` | List registered agents. |
| `POST` | `/v1/agents/{name}/run` | Run an agent, wait for the full result. |
| `POST` | `/v1/agents/{name}/stream` | Run an agent, stream Server-Sent Events. |

Every response carries an `X-Request-ID` header (an inbound one is honoured, so
requests can be traced across services). Every error uses one envelope:

```json
{
  "error": {
    "code": "agent_not_found",
    "message": "No agent named 'ghost'.",
    "request_id": "76f4908f-1e5b-4340-88a7-8930e8585f16"
  }
}
```

Streaming emits `token` frames followed by exactly one terminal `done` or
`error` frame. Errors detectable before streaming starts (unknown agent,
oversized prompt) are returned as real HTTP status codes instead.

---

## Configuration

Every setting is read from the environment with the `PROPILOT_` prefix, or from
`backend/.env`. See [`backend/.env.example`](backend/.env.example) for the full
list. `OPENAI_API_KEY` is also accepted unprefixed.

Nothing in the codebase reads `os.environ` directly — it all goes through
`Settings`, validated once at startup. Production mode rejects `debug=true` and
wildcard CORS origins, and hides the OpenAPI docs.

---

## Repository layout

```
backend/            Python runtime and HTTP API (the live service)
  src/backend/
    api/            FastAPI app, routes, middleware, error envelope
    runtime/        config, logging, tracing, agents, execution
  tests/            pytest suite
agents/             Agent role charters (markdown) — wired up in Phase 2
docs/               Architecture and roadmap
research/           Requirements and architecture decision records
prompts/            Shared engineering standards
apps/, packages/    Reserved for the Phase 3 frontend and shared libraries
server/             Legacy Node prototype, superseded by ADR D-002
```

---

## Known environment issue (macOS)

On the primary development machine, a background process re-applies the macOS
`UF_HIDDEN` flag to files under `~/Documents`. CPython **silently skips hidden
`.pth` files** (`site.py`, `addpackage`), which intermittently breaks editable
installs — `import backend` fails with no explanation, then works again after a
reinstall, then fails again.

This is worked around rather than fought:

- `pytest` sets `pythonpath = ["src"]`, so the suite never depends on it.
- The `Makefile` exports `PYTHONPATH=src` for every target.
- The Docker image installs with `--no-editable`, so no `.pth` is involved.

`make unhide` clears the flag if you need the editable install itself to work.
Linux and CI are unaffected.

---

## Contributing

`make check` must pass before anything is merged: ruff lint, ruff format, mypy
in strict mode, and pytest at ≥90% coverage. CI enforces the same gates and
additionally builds and smoke-tests the container image.
