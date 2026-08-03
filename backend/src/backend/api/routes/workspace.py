"""Workspace data for the product surface.

The same :class:`WorkspaceService` the agent tools call, exposed directly for
the UI. One source of truth means the dashboard and the agent can never
disagree about how many leads need a follow-up.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from backend.api.deps import WorkspaceDep
from backend.api.schemas import ErrorResponse
from backend.runtime.workspace import (
    CalendarSummary,
    Dashboard,
    EmailSummary,
    Lead,
    LeadSummary,
    Suggestion,
    Task,
)

router = APIRouter(prefix="/v1/workspace", tags=["workspace"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Not found"},
}


@router.get("/dashboard", response_model=Dashboard, summary="Everything the home screen needs")
async def dashboard(workspace: WorkspaceDep) -> Dashboard:
    """One round trip for the whole dashboard, so the UI paints in a single pass."""
    return workspace.dashboard()


@router.get("/tasks", response_model=list[Task], summary="Tasks due today or overdue")
async def tasks(workspace: WorkspaceDep, include_done: bool = Query(default=False)) -> list[Task]:
    return workspace.todays_tasks(include_done=include_done)


@router.get("/leads/summary", response_model=LeadSummary, summary="Pipeline summary")
async def lead_summary(workspace: WorkspaceDep) -> LeadSummary:
    return workspace.lead_summary()


@router.get("/leads", response_model=list[Lead], summary="All leads, hottest first")
async def leads(workspace: WorkspaceDep) -> list[Lead]:
    return workspace.leads()


@router.get("/email/summary", response_model=EmailSummary, summary="Inbox summary")
async def email_summary(
    workspace: WorkspaceDep, limit: int = Query(default=5, ge=1, le=50)
) -> EmailSummary:
    return workspace.email_summary(limit=limit)


@router.get("/calendar/summary", response_model=CalendarSummary, summary="Upcoming schedule")
async def calendar_summary(
    workspace: WorkspaceDep, days: int = Query(default=7, ge=1, le=60)
) -> CalendarSummary:
    return workspace.calendar_summary(days=days)


@router.get("/suggestions", response_model=list[Suggestion], summary="AI suggestions")
async def suggestions(workspace: WorkspaceDep) -> list[Suggestion]:
    """Ranked next actions. Each carries the prompt to hand to the agent if accepted."""
    return workspace.suggestions()
