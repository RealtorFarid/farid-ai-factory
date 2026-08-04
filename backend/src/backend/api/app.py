"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import register_exception_handlers
from backend.api.middleware import RequestContextMiddleware
from backend.api.routes import agents, capture, health, runs, workspace
from backend.runtime.config import Settings, get_settings
from backend.runtime.container import Runtime, build_runtime
from backend.runtime.logger import configure_logging, get_logger
from backend.runtime.tracing import configure_tracing, shutdown_tracing

__all__ = ["create_app"]

log = get_logger(__name__)

DESCRIPTION = """\
The agent runtime behind Propilot AI.

**Agents** — `GET /v1/agents`, `POST /v1/agents/{name}/run`,
`POST /v1/agents/{name}/stream`

**Runs and approvals** — `GET /v1/runs`, `GET /v1/runs/{id}`,
`POST /v1/runs/{id}/approvals`, `GET /v1/runs/{id}/events` (SSE)

**Workspace** — `GET /v1/workspace/dashboard` plus per-panel endpoints for
tasks, leads, email, calendar and suggestions.

Tools that send email, book time or complete work are gated: the run pauses,
surfaces a pending approval, and only proceeds once a human decides.
"""


def create_app(settings: Settings | None = None, runtime: Runtime | None = None) -> FastAPI:
    """Build the application.

    ``runtime`` can be injected, which is how the test suite runs the whole
    stack against an offline model and a fixed workspace.
    """
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    container = runtime if runtime is not None else build_runtime(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.tracing_enabled = configure_tracing(settings)

        if not settings.llm_configured:
            log.warning("startup.llm_credentials_missing", hint="set PROPILOT_OPENAI_API_KEY")

        log.info(
            "startup.complete",
            service=settings.app_name,
            version=settings.version,
            environment=settings.environment,
            agents=container.agents.names(),
            tools=len(container.tools),
            gated_tools=[spec.name for spec in container.tools.requiring_approval()],
            persistence="postgres" if container.database is not None else "memory",
        )
        try:
            yield
        finally:
            shutdown_tracing()
            container.shutdown()
            log.info("shutdown.complete")

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    app.state.settings = settings
    app.state.runtime = container
    app.state.registry = container.agents
    app.state.tools = container.tools
    app.state.workspace = container.workspace
    app.state.runs = container.runs
    app.state.bus = container.bus
    app.state.runner = container.runner
    app.state.claims = container.claims
    app.state.extractor = container.extractor
    app.state.transcriber = container.transcriber

    app.add_middleware(RequestContextMiddleware, header_name=settings.request_id_header)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[settings.request_id_header],
    )

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(agents.router)
    app.include_router(runs.router)
    app.include_router(workspace.router)
    app.include_router(capture.router)
    return app
