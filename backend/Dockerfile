# syntax=docker/dockerfile:1.7

# --------------------------------------------------------------------------
# Builder — resolve and install dependencies into a self-contained venv.
# --------------------------------------------------------------------------
# This tag is built on python:3.12-slim-bookworm, which is why the runtime
# stage below must stay on the same base: the venv copied between stages
# hardcodes /usr/local/bin/python3.12.
#
# The uv version floats because astral-sh publishes no 0.12.x image tags.
# Dependency determinism comes from uv.lock + --frozen, not from this tag.
# Pinning both bases by digest is a Phase 4 hardening item.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first: this layer stays cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project --no-editable

# Then the project itself. --no-editable copies the package into site-packages
# as a real directory instead of relying on a .pth path entry.
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# --------------------------------------------------------------------------
# Runtime — no build tools, no uv, no source tree. Just the venv.
# --------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PROPILOT_HOST=0.0.0.0 \
    PROPILOT_PORT=8000 \
    PROPILOT_LOG_FORMAT=json

RUN groupadd --system --gid 1001 propilot \
    && useradd --system --uid 1001 --gid propilot --no-create-home propilot

WORKDIR /app
COPY --from=builder --chown=propilot:propilot /app/.venv /app/.venv

USER propilot
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"]

CMD ["propilot"]
