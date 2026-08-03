"""Liveness and readiness probes.

``/health`` answers "is the process up" and must stay dependency-free so an
orchestrator never restarts a healthy container because a downstream is slow.
``/health/ready`` answers "can this process serve traffic".
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.deps import RegistryDep, SettingsDep
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
async def ready(settings: SettingsDep, registry: RegistryDep) -> ReadyResponse:
    checks = {
        "agents": "ok" if len(registry) else "no agents registered",
        "llm_credentials": "ok" if settings.llm_configured else "missing",
        "tracing": "enabled" if settings.tracing_enabled else "disabled",
    }
    # Tracing is optional, so it never makes the service unready.
    blocking = {"agents": checks["agents"], "llm_credentials": checks["llm_credentials"]}
    status = "ready" if all(v == "ok" for v in blocking.values()) else "degraded"
    return ReadyResponse(status=status, checks=checks)
