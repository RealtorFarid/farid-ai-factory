"""Tool registry.

A tool declares whether it needs human approval; the registry turns that
declaration into enforcement by constructing the PydanticAI tool with
``requires_approval``. Approval is therefore a property of the tool, not
something a caller can forget to apply.

Tools that only read the workspace run unattended. Tools with an effect the
user would not want taken on their behalf — sending mail, booking time — are
gated by :mod:`backend.runtime.approvals`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic_ai.tools import Tool

from backend.runtime.logger import get_logger
from backend.runtime.workspace import EventKind, WorkspaceService

__all__ = ["ToolRegistry", "ToolSpec", "build_default_tools"]

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool plus the policy that governs it."""

    name: str
    description: str
    function: Callable[..., Any]
    requires_approval: bool = False
    category: str = "general"

    def to_pydantic_tool(self) -> Tool[Any]:
        return Tool(
            self.function,
            name=self.name,
            description=self.description,
            requires_approval=self.requires_approval,
        )


class ToolRegistry:
    """An ordered, name-addressable collection of tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"tool {spec.name!r} is already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def requiring_approval(self) -> list[ToolSpec]:
        return [spec for spec in self._tools.values() if spec.requires_approval]

    def as_pydantic_tools(self) -> list[Tool[Any]]:
        return [spec.to_pydantic_tool() for spec in self._tools.values()]

    def __iter__(self) -> Iterator[ToolSpec]:
        return iter(self._tools.values())

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


def build_default_tools(workspace: WorkspaceService) -> ToolRegistry:
    """The tools available to Atlas.

    Closures over ``workspace`` rather than a global, so tests can build a
    registry against a fixture-backed service.
    """
    registry = ToolRegistry()

    # ---- Read-only: no approval needed -----------------------------------

    def list_todays_tasks() -> list[dict[str, Any]]:
        """List the user's tasks that are due today or overdue, most urgent first."""
        return [t.model_dump(mode="json") for t in workspace.todays_tasks()]

    def summarize_leads() -> dict[str, Any]:
        """Summarise the pipeline: totals by stage, follow-ups due, and hottest leads."""
        return workspace.lead_summary().model_dump(mode="json")

    def summarize_inbox() -> dict[str, Any]:
        """Summarise the inbox: unread count, threads awaiting a reply, recent threads."""
        return workspace.email_summary().model_dump(mode="json")

    def summarize_calendar() -> dict[str, Any]:
        """Summarise the next seven days of appointments."""
        return workspace.calendar_summary().model_dump(mode="json")

    def get_lead(lead_id: str) -> dict[str, Any] | None:
        """Look up one lead by id, including budget, stage and notes."""
        lead = workspace.lead(lead_id)
        return lead.model_dump(mode="json") if lead else None

    # ---- Effectful: gated behind human approval --------------------------

    def send_email(lead_id: str, subject: str, body: str) -> dict[str, Any]:
        """Send an email to a lead. Requires the user's approval before it is sent."""
        lead = workspace.lead(lead_id)
        if lead is None:
            return {"sent": False, "reason": f"no lead with id {lead_id!r}"}

        for thread in workspace.emails_needing_response():
            if thread.lead_id == lead_id:
                workspace.mark_email_answered(thread.id)
                break

        log.info("tool.send_email", lead_id=lead_id, subject=subject, chars=len(body))
        return {"sent": True, "to": lead.email, "subject": subject}

    def schedule_showing(
        lead_id: str, starts_at: datetime, location: str, title: str | None = None
    ) -> dict[str, Any]:
        """Book a showing in the calendar. Requires the user's approval before booking."""
        lead = workspace.lead(lead_id)
        if lead is None:
            return {"booked": False, "reason": f"no lead with id {lead_id!r}"}

        event = workspace.schedule_event(
            title=title or f"Showing — {lead.name}",
            starts_at=starts_at,
            location=location,
            kind=EventKind.SHOWING,
            lead_id=lead_id,
        )
        log.info("tool.schedule_showing", lead_id=lead_id, event_id=event.id)
        return {"booked": True, "event": event.model_dump(mode="json")}

    def complete_task(task_id: str) -> dict[str, Any]:
        """Mark a task complete. Requires the user's approval."""
        done = workspace.complete_task(task_id)
        return {"completed": done, "task_id": task_id}

    for spec in (
        ToolSpec(
            name="list_todays_tasks",
            description=list_todays_tasks.__doc__ or "",
            function=list_todays_tasks,
            category="tasks",
        ),
        ToolSpec(
            name="summarize_leads",
            description=summarize_leads.__doc__ or "",
            function=summarize_leads,
            category="leads",
        ),
        ToolSpec(
            name="summarize_inbox",
            description=summarize_inbox.__doc__ or "",
            function=summarize_inbox,
            category="email",
        ),
        ToolSpec(
            name="summarize_calendar",
            description=summarize_calendar.__doc__ or "",
            function=summarize_calendar,
            category="calendar",
        ),
        ToolSpec(
            name="get_lead",
            description=get_lead.__doc__ or "",
            function=get_lead,
            category="leads",
        ),
        ToolSpec(
            name="send_email",
            description=send_email.__doc__ or "",
            function=send_email,
            requires_approval=True,
            category="email",
        ),
        ToolSpec(
            name="schedule_showing",
            description=schedule_showing.__doc__ or "",
            function=schedule_showing,
            requires_approval=True,
            category="calendar",
        ),
        ToolSpec(
            name="complete_task",
            description=complete_task.__doc__ or "",
            function=complete_task,
            requires_approval=True,
            category="tasks",
        ),
    ):
        registry.register(spec)

    return registry
