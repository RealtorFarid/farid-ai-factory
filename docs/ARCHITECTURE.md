# Architecture

How the Propilot AI backend is put together, and why.

Scope: what exists today (Phase 1). Planned work is in [ROADMAP.md](ROADMAP.md);
the reasoning behind stack choices is in [`research/architecture/`](../research/architecture/).

---

## Shape

Two layers, one direction of dependency. `api/` depends on `runtime/`;
`runtime/` never imports from `api/`. The runtime is usable without HTTP —
`backend.runtime.main` proves it.

```
                    HTTP
                      │
        ┌─────────────▼──────────────┐
        │  api/                      │
        │    middleware  request id, access log
        │    errors      one error envelope
        │    routes      health, agents
        │    deps        injection from app.state
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │  runtime/                  │
        │    config      Settings, validated once
        │    logger      structlog
        │    tracing     Langfuse (optional)
        │    agent       registry + model resolution
        │    runner      the only place an agent runs
        └─────────────┬──────────────┘
                      │
                 PydanticAI ──► model provider
```

---

## Request lifecycle

1. **`RequestContextMiddleware`** assigns a correlation id (honouring an inbound
   `X-Request-ID`), binds it to a structlog contextvar so every downstream log
   line carries it, and emits the access line with a duration.
2. **CORS** is applied from `Settings.cors_origins`.
3. **Route handler** resolves the agent from the registry on `app.state` and
   validates the prompt length.
4. **`runner.run_agent`** executes the agent under `asyncio.timeout`, records
   token usage, and logs start/finish.
5. **Exception handlers** convert any failure into the single error envelope.
6. The response leaves with `X-Request-ID` set.

---

## Design decisions

### Settings are injected, never read ambiently

`Settings` is constructed once and validated once. Nothing else reads
`os.environ`. `create_app(settings=..., registry=...)` takes both as arguments,
which is why the test suite can run the entire stack against a stub model with
no monkeypatching of globals.

Production mode is enforced by the config object itself: `debug=true` and
wildcard CORS are validation errors, not review comments.

### One error envelope

Every non-2xx response — validation failure, unknown agent, timeout, unhandled
crash — has the same shape, with a stable machine-readable `code` and the
request id. Unhandled exceptions are logged with a stack trace and reported as a
generic `internal_error`; internals never reach the caller.

### One execution path

`runner.py` is the only module that calls `agent.run()` / `agent.run_stream()`.
Both API routes and the CLI go through it, so timeout, prompt validation, usage
accounting and logging cannot drift apart between transports. When tools, memory
and the approval gate arrive in Phase 2, they attach in exactly one place.

### Streaming reports errors in-band

Once an SSE response starts, the `200` status line is committed and an HTTP
error is no longer possible. So everything checkable up front — agent existence,
prompt length — is checked before the `StreamingResponse` is constructed, and
anything that fails later arrives as a terminal `error` frame.

### Missing credentials degrade, they don't crash

`resolve_model` builds an OpenAI model with a placeholder key when none is
configured, rather than raising at import time. The process boots, `/health`
answers, and `/health/ready` reports `degraded` with
`llm_credentials: missing`. A crash-looping container that cannot answer its own
probe is strictly harder to diagnose.

### A run's outcome is per-action, not binary

A run that proposes several gated actions can have several different outcomes
at once. `RunStatus.PARTIAL` says "you got an answer, but not everything the
agent proposed happened", and every `ToolCallRecord` carries its own
`ToolCallStatus` — `proposed`, `executed`, `denied` or `failed`.

A denial is a legitimate answer rather than an error, but it still means the
user did not get everything proposed, so it yields `PARTIAL`. Reporting
`COMPLETED` after declining an action would misrepresent what happened.

### One bad tool call must not discard approved work

Three layers, because the failure can arrive at three different depths:

1. **Forgiving signatures.** Tool parameters are `str`, not `datetime`. Strict
   annotations fail *inside PydanticAI*, before the function runs, and a model
   that repeats a bad value exhausts the retry budget and aborts the run.
   Parsing in the tool turns that into an ordinary result the model can correct.
2. **A wrapper per tool.** An exception inside a tool becomes
   `{"ok": false, "error": ...}`, so siblings still complete.
3. **`UnexpectedModelBehavior` degrades rather than fails.** If anything
   already executed, the run ends `PARTIAL` with that work intact.

### Proposed is not executed

`tool.proposed` is emitted for a gated call the agent wants to make;
`tool.executed` only after it actually ran. They are separate event types
because a UI that renders "called" for a pending action tells the user
something untrue about a gate whose whole purpose is that nothing has happened
yet.

### Tracing is optional and cannot break the service

Without Langfuse credentials, `configure_tracing` is a no-op. With them, every
failure path — setup and flush — is caught and logged. Observability must never
be the reason the thing being observed goes down.

### Liveness ≠ readiness

`/health` is dependency-free so an orchestrator never restarts a healthy
container because a downstream is slow. `/health/ready` is where dependency
state lives. Tracing is reported there but never blocks readiness.

---

## Testing strategy

- `ALLOW_MODEL_REQUESTS = False` globally: a real model call raises rather than
  silently costing money.
- Agents run against PydanticAI's `TestModel`.
- Every `Settings` is built with `_env_file=None`, so results never depend on a
  developer's local `.env`.
- Failure paths (timeouts, mid-stream errors, tracing failures, missing
  credentials) have dedicated tests — they are the branches that only run when
  something is already wrong.

Gates: ruff, ruff format, mypy `strict`, pytest at ≥90% coverage (currently 99%).
CI additionally builds the image and smoke-tests the running container.

---

## Extension points

| To add | Where it goes |
|---|---|
| A new agent | `runtime/agent.py` → `build_registry`; no API change needed |
| Tools | `runtime/tools.py`, attached in `build_registry`, gated in `runner` |
| Memory | `runtime/memory.py`, threaded through `runner` via `session_id` |
| A different model provider | `runtime/agent.py` → `resolve_model` |
| Multi-agent orchestration | a LangGraph graph behind `runner`, registry unchanged |
| Approval gate | `runtime/events.py` + a pause/resume state in `runner` |

The API surface is versioned under `/v1`, so all of the above can land without
breaking existing callers.
