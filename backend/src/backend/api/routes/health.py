"""Liveness and readiness probes.

``/health`` answers "is the process up" and must stay dependency-free so an
orchestrator never restarts a healthy container because a downstream is slow.
``/health/ready`` answers "can this process serve traffic".
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.deps import RegistryDep, RuntimeDep, SettingsDep
from backend.api.schemas import HealthResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
    )


@router.get("/health/ready", response_model=ReadyResponse, summary="Readiness probe")
def ready(settings: SettingsDep, registry: RegistryDep, runtime: RuntimeDep) -> ReadyResponse:
    """Readiness, including a real round trip to the database.

    Declared `def` rather than `async def`: the database check is blocking, and
    FastAPI runs sync handlers in a worker thread, so a slow database cannot
    stall the event loop and take streaming down with it.
    """
    checks = {
        "agents": "ok" if len(registry) else "no agents registered",
        "llm_credentials": "ok" if settings.llm_configured else "missing",
        "tracing": "enabled" if settings.tracing_enabled else "disabled",
    }

    blocking = {"agents": checks["agents"], "llm_credentials": checks["llm_credentials"]}

    if runtime.database is not None:
        reachable = runtime.database.check()
        checks["database"] = "ok" if reachable else "unreachable"
        # Once persistence is configured, losing it means we cannot serve.
        blocking["database"] = checks["database"]
    else:
        checks["database"] = "in-memory"

    status = "ready" if all(v == "ok" for v in blocking.values()) else "degraded"
    return ReadyResponse(status=status, checks=checks)
