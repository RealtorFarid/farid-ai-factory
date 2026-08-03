# Roadmap

Measured against the functional requirements in
[`research/architecture/REQUIREMENTS.md`](../research/architecture/REQUIREMENTS.md).

| Capability | Status |
|---|---|
| Multi-Agent | Phase 3 — registry exists, one agent registered |
| Browser Automation | Phase 3 |
| MCP Support | Phase 3 |
| Memory | Phase 2 |
| Evaluation | Phase 3 |
| Tracing | ✅ Phase 1 (Langfuse, optional) |
| LLM Routing | Phase 2 |
| Tool Calling | Phase 2 |
| Human in the Loop | Phase 2 |

---

## Phase 0 — Foundations ✅

- [x] Root `.gitignore` covering `.env`, venvs, `node_modules`, caches
- [x] `backend/.env.example` documenting every setting
- [x] Fixed the broken `[project.scripts]` entry point
- [x] Removed the import-time `print` side effect from `backend/__init__.py`
- [x] Dropped declared-but-unused dependencies (LangGraph, LiteLLM) until used
- [x] Root `README.md`

## Phase 1 — A real runtime ✅

- [x] Python 3.12 (was 3.9, past end of life)
- [x] `Settings` via pydantic-settings, validated once, with production hardening
- [x] structlog logging: console in development, JSON in production, no `print`
- [x] FastAPI service: health, readiness, agent listing, run, SSE streaming
- [x] Single error envelope with stable codes and request-id correlation
- [x] pytest suite — 68 tests, 99% coverage, no network access
- [x] GitHub Actions CI: ruff, format, mypy strict, pytest, image build + smoke test
- [x] Langfuse tracing, optional and failure-tolerant
- [x] Multi-stage Dockerfile (non-root, healthcheck) and compose stack
- [x] `docs/ARCHITECTURE.md`, `Makefile`

## Phase 2 — Close the requirements gap

Target: an agent that can *act*, with a human in the loop.

- [ ] `runtime/tools.py` — tool registry wired into `build_registry`
- [ ] `runtime/events.py` — event bus (agent lifecycle, tool calls, approvals)
- [ ] Human-in-the-loop approval gate: pause a run, surface the pending action,
      resume on approval. A core principle in REQUIREMENTS.md; must land before
      any tool can affect the outside world.
- [ ] `runtime/memory.py` — PostgreSQL + pgvector, SQLAlchemy, Alembic.
      Session memory first, semantic recall second. `session_id` is already
      accepted and logged; make it mean something.
- [ ] `runtime/llm.py` — LiteLLM routing, model fallback, cost accounting
- [ ] Rate limiting and per-request cost caps
- [ ] Agent loader: parse `agents/*.md` into runtime agents, and fill the seven
      empty charters (Architect, Backend, Frontend, Integration, Marketing, QA,
      RealEstate)

## Phase 3 — Multi-agent and evidence

- [ ] LangGraph orchestration: supervisor routing to specialists
- [ ] Fill in `research/architecture/SCORECARD.md` by actually benchmarking the
      candidates, then resolve every 🔍 in `STACK.md` to ✅/❌ with an ADR.
      The scorecard is currently an empty table behind decisions already marked
      accepted.
- [ ] Evaluation harness with a golden dataset of real-estate tasks. "AI
      Accuracy" is a stated CEO metric with no instrument today.
- [ ] MCP client support
- [ ] Browser automation (Browser Use), sandboxed and behind the approval gate
- [ ] Frontend in `apps/web`: React + Vite, streaming output, approval UI

## Phase 4 — Production

- [ ] Authentication and per-tenant isolation
- [ ] Managed secrets (the current model is a local `.env`)
- [ ] Postgres and Langfuse in the compose stack; deployment manifests in
      `infrastructure/`
- [ ] Load testing and autoscaling
- [ ] Persisted run history and an audit trail

---

## Open items carried forward

- **`server/` and `packages/core/`** are a superseded Node prototype. ADR D-002
  chose Python; nothing imports them. They should be deleted — pending approval.
- **Root `package.json`** describes a Node project that no longer exists.
- **Empty directories** (`apps/`, `packages/*`, `infrastructure/`, `workflows/`)
  are placeholders for Phase 3–4 work.
