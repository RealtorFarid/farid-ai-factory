# Propilot AI

An AI operating system for real-estate professionals.

This repository holds the agent runtime and the HTTP API in front of it.

**Status:** Sprints 1–3 complete. A FastAPI runtime with an agent that can read
your workspace and *act* on it — behind a human approval gate — plus a React
product surface on top. Memory, multi-agent orchestration and evaluation are
next. See [docs/ROADMAP.md](docs/ROADMAP.md).

The core idea: Atlas reads your tasks, leads, inbox and calendar before it
answers, and when it wants to send an email or book a showing the run **pauses**
until you approve it. That gate is structural, not advisory — a tool declares
`requires_approval` and there is no code path that runs it without a decision.

---

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (uv will fetch it).

```bash
git clone https://github.com/RealtorFarid/farid-ai-factory.git
cd farid-ai-factory

cp backend/.env.example backend/.env    # then add your OpenAI key
make install
make web-install
make dev                                # API on :8000, web on :5173
```

Open <http://localhost:5173>. The API's own docs are at
<http://127.0.0.1:8000/docs>.

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
| `make db-start` · `db-create` · `db-migrate` | Local Postgres setup |
| `make db-revision m="..."` | Autogenerate a migration |
| `make db-check` | Fail if models have drifted from migrations |

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness. Dependency-free, always 200 when the process is up. |
| `GET` | `/health/ready` | Readiness: agents registered, credentials present, tracing state. |
| `GET` | `/v1/agents` | List registered agents. |
| `GET` | `/v1/agents/tools` | Every tool, and whether it is gated behind approval. |
| `POST` | `/v1/agents/{name}/run` | Run an agent; returns a run, possibly `awaiting_approval`. |
| `POST` | `/v1/agents/{name}/stream` | Run an agent, streaming its events. |
| `GET` | `/v1/runs` · `/v1/runs/{id}` | Run history and detail. |
| `POST` | `/v1/runs/{id}/approvals` | Approve or deny pending actions; resumes the run. |
| `GET` | `/v1/runs/{id}/events` | SSE stream of a run, with `Last-Event-ID` resume. |
| `GET` | `/v1/workspace/dashboard` | Everything the home screen needs, in one round trip. |
| `GET` | `/v1/workspace/{tasks,leads,email/summary,calendar/summary,suggestions}` | Per-panel data. |

The workspace endpoints and the agent's tools are backed by the **same
service**, so an agent can never quote a number the dashboard disagrees with.

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

## Persistence

Off by default. Unset `PROPILOT_DATABASE_URL` and everything runs in memory —
which is what the demo, the e2e suite and most tests use. Set it and runs,
approvals and the workspace survive a restart, with no other code change:
storage is chosen in one place (`runtime/container.py`) behind protocols the
rest of the system already depended on.

```bash
make db-start db-create        # local Postgres 17
echo 'PROPILOT_DATABASE_URL=postgresql+psycopg://'$(whoami)'@localhost:5432/propilot' >> backend/.env
make db-migrate
make run
```

Three things in the schema exist before any real data, because none of them can
be added later ([D-022](research/architecture/DECISIONS.md)):

| | Why it cannot wait |
|---|---|
| **Tenancy** (`org_id` everywhere) | Adding it after rows exist is a migration with no correct answer |
| **Claim Ledger** (source, confidence, legal basis, sensitivity, decay) | A fact stored without a source is permanently unverifiable — there is nobody left to ask |
| **Consent Ledger** (per person, per channel, per jurisdiction) | Contact history without consent records is a compliance problem, not a schema problem |

Claims are append-only: corrections supersede rather than overwrite, so what was
believed on any past date stays reconstructable. Protected attributes — the ones
fair housing law covers — cannot be recorded by inference, and are withheld from
any caller that does not explicitly ask for them.

Migrations are a deploy step, never run on startup ([D-023](research/architecture/DECISIONS.md)).
CI runs `alembic check`, so models drifting from migrations fails the build.

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

## Known environment issue (macOS + iCloud)

**This repository is inside `~/Documents`, which is iCloud-synced with
"Optimise Mac Storage" on.** That causes two distinct, genuinely confusing
failures, both confirmed by inspection rather than guessed at:

1. **Hidden `.pth` files.** The sync agent sets the macOS `UF_HIDDEN` flag on
   files in `backend/.venv`. CPython **silently skips hidden `.pth` files**
   (`site.py`, `addpackage`) — no error, no warning — so editable installs
   break at random: `import backend` fails, works after a reinstall, then fails
   again. Every `.pth` in the venv was affected, including coverage's.

2. **Dataless (evicted) dependency files.** Files get flagged
   `hidden,compressed,dataless`. Importing one blocks in
   `importlib.get_data` until iCloud re-downloads it, which can hang for
   minutes. Symptom: the server starts, prints nothing, and never listens.

Worked around rather than fought:

- `pytest` sets `pythonpath = ["src"]` and the `Makefile` exports
  `PYTHONPATH=src`, so neither depends on `.pth`.
- The Docker image installs with `--no-editable` — no `.pth`, no iCloud.
- `make unhide` clears the hidden flag; `make materialise` force-downloads the
  venv.

**The real fix is to move this repository out of `~/Documents`** (e.g. to
`~/dev/farid-ai-factory`), or to turn off Optimise Mac Storage. Linux and CI are
completely unaffected, which is why CI is the authoritative verification.

---

## Contributing

`make check` must pass before anything is merged: ruff lint, ruff format, mypy
in strict mode, and pytest at ≥90% coverage. CI enforces the same gates and
additionally builds and smoke-tests the container image.
