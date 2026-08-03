"""Agent discovery and execution endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import asdict

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from backend.api.deps import RegistryDep, SettingsDep
from backend.api.middleware import get_request_id
from backend.api.schemas import (
    AgentInfo,
    AgentListResponse,
    ErrorResponse,
    RunRequest,
    RunResponse,
    UsageInfo,
)
from backend.runtime.logger import get_logger
from backend.runtime.runner import (
    AgentTimeoutError,
    DoneEvent,
    TokenEvent,
    run_agent,
    stream_agent,
    validate_prompt,
)

router = APIRouter(prefix="/v1/agents", tags=["agents"])
log = get_logger(__name__)

_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Unknown agent"},
    status.HTTP_413_CONTENT_TOO_LARGE: {
        "model": ErrorResponse,
        "description": "Prompt exceeds the configured limit",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "Malformed request body",
    },
    status.HTTP_504_GATEWAY_TIMEOUT: {"model": ErrorResponse, "description": "Agent timed out"},
}


@router.get("", response_model=AgentListResponse, summary="List available agents")
async def list_agents(registry: RegistryDep) -> AgentListResponse:
    return AgentListResponse(
        agents=[
            AgentInfo(name=spec.name, description=spec.description, model=spec.model)
            for spec in registry
        ],
        default=registry.default.name,
    )


@router.post(
    "/{agent_name}/run",
    response_model=RunResponse,
    responses=_ERROR_RESPONSES,
    summary="Run an agent and wait for the complete result",
)
async def run(
    agent_name: str,
    body: RunRequest,
    request: Request,
    registry: RegistryDep,
    settings: SettingsDep,
) -> RunResponse:
    spec = registry.get(agent_name)  # raises AgentNotFoundError -> 404
    validate_prompt(body.prompt, settings.max_prompt_chars)  # -> 413

    outcome = await run_agent(
        spec, body.prompt, timeout_seconds=settings.agent_timeout_seconds
    )  # -> 504 on timeout

    return RunResponse(
        agent=spec.name,
        model=spec.model,
        output=outcome.output,
        usage=UsageInfo(**asdict(outcome.usage)),
        duration_ms=outcome.duration_ms,
        request_id=get_request_id(request),
    )


def _sse(event: str, data: dict[str, object]) -> str:
    """Encode one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/{agent_name}/stream",
    responses=_ERROR_RESPONSES,
    summary="Run an agent and stream the result as Server-Sent Events",
    response_class=StreamingResponse,
)
async def stream(
    agent_name: str,
    body: RunRequest,
    request: Request,
    registry: RegistryDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Stream token deltas.

    Frames are ``token`` (incremental text), then exactly one terminal frame:
    ``done`` on success or ``error`` on failure. Failures are reported in-band
    because the 200 status line is already committed once streaming starts —
    so both the agent lookup and prompt validation happen up front, where they
    can still return a real HTTP error.
    """
    spec = registry.get(agent_name)
    validate_prompt(body.prompt, settings.max_prompt_chars)
    request_id = get_request_id(request)

    async def frames() -> AsyncIterator[str]:
        try:
            async for event in stream_agent(
                spec, body.prompt, timeout_seconds=settings.agent_timeout_seconds
            ):
                if isinstance(event, TokenEvent):
                    yield _sse("token", {"delta": event.delta})
                elif isinstance(event, DoneEvent):
                    yield _sse(
                        "done",
                        {
                            "agent": spec.name,
                            "model": spec.model,
                            "output": event.output,
                            "usage": asdict(event.usage),
                            "duration_ms": event.duration_ms,
                            "request_id": request_id,
                        },
                    )
        except AgentTimeoutError as exc:
            yield _sse(
                "error", {"code": "agent_timeout", "message": str(exc), "request_id": request_id}
            )
        except Exception as exc:  # reported in-band; the status line is committed
            log.exception("agent.stream.failed", agent=spec.name, error=str(exc))
            yield _sse(
                "error",
                {
                    "code": "internal_error",
                    "message": "An internal error occurred.",
                    "request_id": request_id,
                },
            )

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx)
        },
    )
