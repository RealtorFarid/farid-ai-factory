"""Workspace domain models.

These are the API contract as well as the internal representation. They are
plain pydantic models with no persistence concerns, so the Phase 2 database
layer can map onto them without changing anything above.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CalendarEvent",
    "CalendarSummary",
    "Dashboard",
    "EmailSummary",
    "EmailThread",
    "EventKind",
    "Impact",
    "Lead",
    "LeadStage",
    "LeadSummary",
    "Suggestion",
    "Task",
    "TaskPriority",
    "TaskStatus",
]


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---- Enumerations --------------------------------------------------------


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class LeadStage(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    SHOWING = "showing"
    OFFER = "offer"
    CLOSED = "closed"
    LOST = "lost"


class EventKind(StrEnum):
    SHOWING = "showing"
    CALL = "call"
    MEETING = "meeting"
    OPEN_HOUSE = "open_house"


class Impact(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ---- Entities ------------------------------------------------------------


class Task(DomainModel):
    id: str
    title: str
    due_at: datetime
    priority: TaskPriority
    status: TaskStatus
    lead_id: str | None = None


class Lead(DomainModel):
    id: str
    name: str
    email: str
    phone: str
    stage: LeadStage
    budget_min: int
    budget_max: int
    last_contact_at: datetime
    score: int = Field(ge=0, le=100, description="Engagement score, 0-100.")
    notes: str


class EmailThread(DomainModel):
    id: str
    subject: str
    sender: str
    preview: str
    received_at: datetime
    unread: bool
    needs_response: bool
    lead_id: str | None = None


class CalendarEvent(DomainModel):
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str
    kind: EventKind
    lead_id: str | None = None


class Suggestion(DomainModel):
    id: str
    title: str
    rationale: str
    impact: Impact
    prompt: str = Field(description="The prompt to send to the agent if accepted.")


# ---- Aggregates ----------------------------------------------------------


class LeadSummary(DomainModel):
    total: int
    by_stage: dict[str, int]
    new_this_week: int
    needs_follow_up: int
    hottest: list[Lead]


class EmailSummary(DomainModel):
    unread: int
    needs_response: int
    threads: list[EmailThread]


class CalendarSummary(DomainModel):
    today_count: int
    next_event: CalendarEvent | None
    events: list[CalendarEvent]


class Dashboard(DomainModel):
    """Everything the home screen needs, in one round trip."""

    generated_at: datetime
    tasks: list[Task]
    leads: LeadSummary
    emails: EmailSummary
    calendar: CalendarSummary
    suggestions: list[Suggestion]
