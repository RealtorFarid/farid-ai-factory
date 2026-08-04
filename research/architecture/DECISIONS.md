# Architecture Decisions

## D-001

Question

Should we build our own agent framework?

Decision

No.

Reason

We will build on top of mature frameworks instead of reinventing the wheel.

Candidates

- OpenAI Agents SDK
- PydanticAI
- LangGraph

Status

Accepted

---

## D-002

Question

Node or Python for AI?

Decision

Python

Reason

Best ecosystem for AI, Agents, MCP, Browser automation and evaluation.

Status

Accepted

---

## D-003

Question

Which Python version?

Decision

3.12, floor set at `requires-python = ">=3.12"`.

Reason

The project was pinned to 3.9, which reached end of life in October 2025.
LangGraph and PydanticAI are actively dropping 3.9. Migrating later would have
been strictly more expensive than migrating before the code existed. 3.12 is
supported by every dependency in the stack; 3.13 was not chosen because some
transitive dependencies still ship 3.12-only wheels.

Status

Accepted

---

## D-004

Question

How are dependencies declared before they are used?

Decision

They are not. A dependency enters `pyproject.toml` in the same change that
imports it.

Reason

`fastapi`, `langgraph`, `litellm` and `langfuse` were all declared and locked
while nothing imported them. That makes the dependency list describe an
aspiration rather than the program, and it makes the lockfile carry supply-chain
risk for code that does not exist. LangGraph and LiteLLM were removed and will
return in Phase 2/3 alongside their first use. Langfuse stayed because tracing
now actually uses it.

Status

Accepted

---

## D-005

Question

Should the service fail to start when LLM credentials are missing?

Decision

No. It boots, serves `/health`, and reports `degraded` on `/health/ready` with
`llm_credentials: missing`.

Reason

A container that crash-loops before it can answer its own health probe is
harder to diagnose than one that reports precisely what it lacks. Orchestrators
and humans both get a clearer signal. Agent requests then fail with an
authentication error, which is the honest outcome.

Consequence

`resolve_model` constructs the OpenAI provider with a placeholder key when none
is configured, rather than letting PydanticAI raise at import time.

Status

Accepted

---

## D-021

Question

Async or synchronous SQLAlchemy?

Decision

Synchronous. Async callers offload through `anyio.to_thread` where it matters.

Reason

Queries here are small and indexed; the database is not the latency budget.
FastAPI already runs plain `def` handlers in a worker thread and PydanticAI
runs sync tools off the event loop, so the sync path is non-blocking where it
counts without any extra machinery. The async ORM costs more to own — session
lifecycles, greenlet context, lazy-load surprises — and this codebase must stay
comprehensible to one engineer for years. Revisit only if measurement shows
connection concurrency is the bottleneck.

Status

Accepted

---

## D-022

Question

What must the first schema contain, before any real data exists?

Decision

Tenancy, provenance and consent. Specifically: `org_id` on every business row,
a `claims` table where each fact carries source, confidence, legal basis,
sensitivity and decay, and a `consents` table keyed per person, per channel,
per jurisdiction.

Reason

These three cannot be retrofitted. Adding `org_id` after rows exist is a
migration with no correct answer. A fact stored without a source is
permanently unverifiable — there is nobody to ask later. And contact history
accumulated before a consent record is a compliance problem, not a schema
problem: CASL requires demonstrable express consent and TCPA damages are per
message.

Claims are append-only. A correction inserts a new row and marks the old one
superseded, so what was believed on any past date stays reconstructable.

Consequence

`claims` and `consents` exist with no feature writing to them yet. That is
deliberate: the capture pipeline is the first writer, and it must not be the
thing that decides the shape.

Status

Accepted

---

## D-023

Question

Does the application run migrations on startup?

Decision

No. `alembic upgrade head` is a separate deploy step, shipped in the same image.

Reason

Auto-migrating on boot means a rolling deploy can have two versions racing to
alter the same schema, and a failed migration takes down every replica at once
rather than one deploy job. CI additionally runs `alembic check`, so models
drifting from migrations fails the build rather than surfacing in production.

Status

Accepted

---

## D-006

Question

How are errors reported to API clients?

Decision

One envelope for every non-2xx response:
`{"error": {"code", "message", "request_id", "details?"}}`, with `code` treated
as stable API surface.

Reason

Clients need to branch on failures without parsing prose. A single shape means
a client writes one error path instead of one per endpoint. Carrying the
request id into the body — not just the header — means a user can quote an
error and have it be traceable in the logs.

Status

Accepted