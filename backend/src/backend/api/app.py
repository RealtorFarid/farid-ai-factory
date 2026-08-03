"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import register_exception_handlers
from backend.api.middleware import RequestContextMiddleware
from backend.api.routes import agents, health
from backend.runtime.agent import AgentRegistry, build_registry
from backend.runtime.config import Settings, get_settings
from backend.runtime.logger import configure_logging, get_logger
from backend.runtime.tracing import configure_tracing, shutdown_tracing

__all__ = ["create_app"]

log = get_logger(__name__)

DESCRIPTION = """\
The agent runtime behind Propilot AI.

* `GET  /health` — liveness
* `GET  /health/ready` — readiness
* `GET  /v1/agents` — list agents
* `POST /v1/agents/{name}/run` — run an agent, wait for the full result
* `POST /v1/agents/{name}/stream` — run an agent, stream Server-Sent Events
"""


def create_app(
    settings: Settings | None = None,
    registry: AgentRegistry | None = None,
) -> FastAPI:
    """Build the application.

    Both dependencies can be injected, which is what the test suite does to run
    the whole stack against a stub model with no network access.
    """
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.registry = registry if registry is not None else build_registry(settings)
        app.state.tracing_enabled = configure_tracing(settings)

        if not settings.llm_configured:
            log.warning("startup.llm_credentials_missing", hint="set PROPILOT_OPENAI_API_KEY")

        log.info(
            "startup.complete",
            service=settings.app_name,
            version=settings.version,
            environment=settings.environment,
            agents=app.state.registry.names(),
        )
        try:
            yield
        finally:
            shutdown_tracing()
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

    # State is also set outside the lifespan so that constructing the app is
    # enough for tests and tooling that never trigger startup.
    app.state.settings = settings
    app.state.registry = registry if registry is not None else build_registry(settings)

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
    return app
