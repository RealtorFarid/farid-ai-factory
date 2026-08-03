"""Run inspection, the approval gate, and the live event stream."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from backend.api.deps import BusDep, RunnerDep, RunStoreDep
from backend.api.middleware import get_request_id
from backend.api.schemas import (
    ApprovalRequest,
    ErrorResponse,
    RunListResponse,
    RunResponse,
)
from backend.api.sse import SSE_HEADERS, sse_frame
from backend.runtime.logger import get_logger
from backend.runtime.runs import ApprovalDecision

router = APIRouter(prefix="/v1/runs", tags=["runs"])
log = get_logger(__name__)

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Unknown run"},
    status.HTTP_409_CONFLICT: {
        "model": ErrorResponse,
        "description": "The run is not awaiting approval",
    },
    status.HTTP_422_UNPROCESSABLE_CONTENT: {
        "model": ErrorResponse,
        "description": "Malformed request body, or an unknown tool_call_id",
    },
}


@router.get("", response_model=RunListResponse, summary="List recent runs")
async def list_runs(
    runs: RunStoreDep,
    limit: int = Query(default=50, ge=1, le=200),
    session_id: str | None = Query(default=None),
) -> RunListResponse:
    return RunListResponse(
        runs=[RunResponse.from_run(r) for r in runs.list(limit=limit, session_id=session_id)]
    )


@router.get(
    "/{run_id}",
    response_model=RunResponse,
    responses=_ERRORS,
    summary="Fetch one run",
)
async def get_run(run_id: str, runs: RunStoreDep) -> RunResponse:
    return RunResponse.from_run(runs.get(run_id))  # -> 404


@router.post(
    "/{run_id}/approvals",
    response_model=RunResponse,
    responses=_ERRORS,
    summary="Approve or deny the actions a run is waiting on",
)
async def resolve_approvals(run_id: str, body: ApprovalRequest, runner: RunnerDep) -> RunResponse:
    """Resolve a paused run.

    Every pending approval should get a decision. Any that are omitted are
    denied — silence must never be read as consent.
    """
    decisions = [
        ApprovalDecision(tool_call_id=d.tool_call_id, approved=d.approved, reason=d.reason)
        for d in body.decisions
    ]
    run = await runner.resume(run_id, decisions)
    return RunResponse.from_run(run)


@router.get(
    "/{run_id}/events",
    responses=_ERRORS,
    summary="Stream a run's events as Server-Sent Events",
    response_class=StreamingResponse,
)
async def stream_events(
    run_id: str,
    request: Request,
    runs: RunStoreDep,
    bus: BusDep,
    last_event_id: int | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Attach to a run, live.

    Everything already emitted is replayed first, so a client that connects
    late — or reconnects after a dropped connection — sees the whole run. A
    browser resends `Last-Event-ID` automatically; pass it and the replay
    starts from there instead of the beginning.

    Frames mirror the event bus: `run.started`, `run.token`, `tool.called`,
    `approval.required`, `approval.resolved`, `run.resumed`, and one terminal
    `run.completed` or `run.failed`.
    """
    runs.get(run_id)  # -> 404 before the status line is committed
    replay_from = last_event_id or 0
    request_id = get_request_id(request)

    async def frames() -> AsyncIterator[str]:
        try:
            async with bus.subscribe(run_id, replay_from=replay_from) as events:
                async for event in events:
                    if await request.is_disconnected():
                        break
                    yield sse_frame(event.type.value, event.to_payload(), event_id=event.sequence)
        except Exception as exc:
            log.exception("runs.stream_failed", run_id=run_id, error=str(exc))
            yield sse_frame(
                "error",
                {
                    "code": "internal_error",
                    "message": "An internal error occurred.",
                    "request_id": request_id,
                },
            )

    return StreamingResponse(frames(), media_type="text/event-stream", headers=SSE_HEADERS)
