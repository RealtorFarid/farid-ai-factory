# Engineering standards

Shared rules for every contributor to Propilot AI, human or agent. These are
enforced by `make check` and CI, not by review alone.

---

## Gates

Nothing merges unless all of these pass:

```bash
make check      # ruff lint + ruff format + mypy strict + pytest ≥90% coverage
```

CI runs the same gates and additionally builds the container image and
smoke-tests the running service.

---

## Python

- **Python 3.12+.** Type annotations on every function signature, including
  tests. `mypy --strict` passes with no new `type: ignore` unless the reason is
  in a comment.
- **`from __future__ import annotations`** at the top of every module.
- **No `print`.** Use `backend.runtime.logger.get_logger`. Log events are
  lowercase dotted names (`agent.run.started`), with data as keyword arguments —
  never interpolated into the message.
- **No ambient environment reads.** Everything goes through `Settings`.
  If you need a new knob, add it to `config.py` *and* `.env.example`.
- **No import-time side effects.** Importing a module must not print, read the
  environment, open a socket, or construct a client.
- Line length 100. Formatting is `ruff format`; do not hand-align.

## Design

- **One way to do a thing.** Agent execution lives in `runner.py` and nowhere
  else. Before adding a second path, change the first one.
- **Dependencies point inward.** `api/` may import `runtime/`. `runtime/` may
  never import `api/`.
- **Inject, don't reach.** Shared objects live on `app.state` and arrive via
  `deps.py`. Module-level singletons are for configuration only.
- **Fail loudly at the edge, degrade gracefully in the middle.** Reject bad
  input at the boundary with a precise status code. Never let an optional
  subsystem (tracing, metrics) take down a required one.
- **Don't declare what you don't use.** A dependency in `pyproject.toml` that
  nothing imports is a promise, not a feature. Add it when you use it.

## Errors

- Every non-2xx response uses the envelope in `api/errors.py`. Add a handler
  there rather than returning an ad-hoc `JSONResponse`.
- Error `code` values are stable API surface — clients switch on them. Renaming
  one is a breaking change.
- Internal detail never reaches the caller. Log the cause, return a generic
  message.

## Testing

- **Tests never touch the network.** Model calls go through `TestModel`;
  `ALLOW_MODEL_REQUESTS` stays disabled.
- **Tests never read the developer's `.env`.** Build `Settings` with
  `_env_file=None`.
- Cover the failure path, not just the happy path. Timeouts, malformed input,
  and dependency failures are where production incidents come from.
- A test name states the behaviour (`test_stream_timeout_is_reported_in_band`),
  not the function under test.

## Security

- **Never commit a secret.** `.env` is gitignored and CI fails if one is
  tracked. If a key is exposed, rotate it first and clean history second.
- Secrets are `SecretStr` in config so they cannot leak through `repr`.
- Containers run as a non-root user.
- Production rejects wildcard CORS and `debug=true` at config validation time.

## Documentation

- A module docstring says what the module is *for* and what it deliberately does
  not do. Comments explain *why*; the code already says what.
- Update `docs/ARCHITECTURE.md` when you change a seam, and
  `docs/ROADMAP.md` when you finish or move an item.
- Record architectural decisions as ADRs in `research/architecture/DECISIONS.md`,
  including the options rejected and the reason.
