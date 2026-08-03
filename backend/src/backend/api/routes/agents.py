"""Agent discovery and execution endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, status
from fastapi.responses import StreamingResponse

from backend.api.deps import RegistryDep, RunnerDep, ToolsDep
from backend.api.middleware import get_request_id
from backend.api.schemas import (
    AgentInfo,
    AgentListResponse,
    ErrorResponse,
    RunRequest,
    RunResponse,
    ToolInfo,
    ToolListResponse,
)
from backend.api.sse import SSE_HEADERS, sse_frame
from backend.runtime.logger import get_logger

router = APIRouter(prefix="/v1/agents", tags=["agents"])
log = get_logger(__name__)

_ERRORS: dict[int | str, dict[str, object]] = {
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


@router.get("/tools", response_model=ToolListResponse, summary="List agent tools")
async def list_tools(tools: ToolsDep) -> ToolListResponse:
    """Every tool an agent can call, and whether it is gated behind approval."""
    return ToolListResponse(
        tools=[
            ToolInfo(
                name=spec.name,
                description=spec.description.strip(),
                category=spec.category,
                requires_approval=spec.requires_approval,
            )
            for spec in tools
        ]
    )


@router.post(
    "/{agent_name}/run",
    response_model=RunResponse,
    responses=_ERRORS,
    summary="Run an agent and wait for it to finish or pause for approval",
)
async def run(agent_name: str, body: RunRequest, runner: RunnerDep) -> RunResponse:
    """Execute a run to completion.

    A run that calls a gated tool comes back with `status: awaiting_approval`
    and a populated `pending_approvals` list rather than a final answer;
    resolve it via `POST /v1/runs/{id}/approvals`.
    """
    result = await runner.start(agent_name, body.prompt, session_id=body.session_id)
    return RunResponse.from_run(result)


@router.post(
    "/{agent_name}/stream",
    responses=_ERRORS,
    summary="Run an agent and stream its events as they happen",
    response_class=StreamingResponse,
)
async def stream(
    agent_name: str,
    body: RunRequest,
    request: Request,
    registry: RegistryDep,
    runner: RunnerDep,
) -> StreamingResponse:
    """Start a run and stream it.

    The run executes in the background and its events are relayed as they are
    published: `run.started`, `run.token`, `tool.called`, `approval.required`,
    then a terminal `run.completed` / `run.failed`.

    Errors that can be detected up front — unknown agent, oversized prompt —
    are raised before the stream opens, so they surface as real HTTP status
    codes rather than as an in-band frame.
    """
    spec = registry.get(agent_name)  # -> 404
    request_id = get_request_id(request)

    # Start before the response opens so validation errors are real HTTP
    # errors, and so the run id is known to the first frame.
    started = await runner.begin(agent_name, body.prompt, session_id=body.session_id)

    async def frames() -> AsyncIterator[str]:
        try:
            # The bus replays from sequence 0, so nothing published between
            # begin() and subscribe() can be lost.
            async with runner.bus.subscribe(started.run.id) as events:
                async for event in events:
                    if await request.is_disconnected():
                        break
                    yield sse_frame(event.type.value, event.to_payload(), event_id=event.sequence)
        except Exception as exc:
            log.exception("agents.stream_failed", agent=spec.name, error=str(exc))
            yield sse_frame(
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
        headers={**SSE_HEADERS, "X-Run-Id": started.run.id},
    )
