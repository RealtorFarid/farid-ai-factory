# Roadmap

Measured against the functional requirements in
[`research/architecture/REQUIREMENTS.md`](../research/architecture/REQUIREMENTS.md).

| Capability | Status |
|---|---|
| Multi-Agent | Sprint 4 — registry exists, one agent registered |
| Browser Automation | Sprint 5 |
| MCP Support | Sprint 5 |
| Memory | Sprint 4 — runs are in-process and lost on restart |
| Evaluation | Sprint 5 |
| Tracing | ✅ Sprint 1 (Langfuse, optional) |
| LLM Routing | Sprint 4 |
| Tool Calling | ✅ Sprint 2 — 8 tools, 5 read-only, 3 gated |
| Human in the Loop | ✅ Sprint 2 — structural, not advisory |

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

## Sprint 2 — An agent that can act ✅

- [x] `runtime/tools.py` — tool registry. A tool declares `requires_approval`
      and the registry constructs it that way, so the gate cannot be bypassed
      by forgetting to check it.
- [x] `runtime/events.py` — event bus with a bounded per-run replay buffer.
      Late and reconnecting subscribers see the whole run; a lagging subscriber
      is dropped rather than allowed to stall the run.
- [x] `runtime/runs.py` + `runtime/orchestrator.py` — run lifecycle and the
      approval gate. Omitted decisions are **denied**: silence is never consent.
- [x] SSE approval stream, with `Last-Event-ID` resume
- [x] `runtime/workspace/` — the real-estate domain behind a store protocol,
      backing both the agent tools and the REST API from one service

## Sprint 3 — The product surface ✅

- [x] React 19 + Vite + TypeScript app in `apps/web`
- [x] Six real, data-backed screens — Today, Ask Atlas, Leads, Inbox, Calendar,
      Activity. No placeholder pages.
- [x] Streaming chat with inline approval cards showing the exact tool and
      arguments before anything runs
- [x] Token-based design system, light and dark, responsive to 320px
- [x] Skeleton loading states that mirror real row layout, plus offline and
      error states with retry
- [x] CI job: typecheck, lint, build

## Sprint 4 — Multi-agent and evidence

- [ ] **Persistence.** `RunStore` and `InMemoryWorkspaceStore` are in-process:
      a restart loses every run and resets the workspace, and a second worker
      would not see the first one's runs. PostgreSQL + pgvector behind the
      existing protocols. This is the top blocker for real use.
- [ ] `runtime/memory.py` — session memory, then semantic recall. `session_id`
      is already accepted, logged and used to group runs; make it mean more.
- [ ] `runtime/llm.py` — LiteLLM routing, model fallback, cost accounting
- [ ] Rate limiting and per-request cost caps
- [ ] Agent loader: parse `agents/*.md` into runtime agents, and fill the seven
      empty charters
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
