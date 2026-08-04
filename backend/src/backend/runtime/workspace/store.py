"""Workspace persistence.

:class:`WorkspaceStore` is the seam. :class:`InMemoryWorkspaceStore` is the
Phase 1/2 implementation: a seeded dataset held in process. Phase 2 replaces it
with PostgreSQL without touching the service, tools or API above it.

The seed is anchored to "now" at construction time so the dashboard always has
today's tasks and today's calendar, whenever the process happens to start.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from backend.runtime.workspace.models import (
    CalendarEvent,
    EmailThread,
    EventKind,
    Impact,
    Lead,
    LeadStage,
    Suggestion,
    Task,
    TaskPriority,
    TaskStatus,
)

__all__ = ["InMemoryWorkspaceStore", "WorkspaceSeed", "WorkspaceStore", "default_seed", "utcnow"]


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class WorkspaceSeed:
    """The starter dataset, shared by the in-memory store and the database seeder."""

    leads: list[Lead]
    tasks: list[Task]
    emails: list[EmailThread]
    events: list[CalendarEvent]
    suggestions: list[Suggestion]


def default_seed(base: datetime) -> WorkspaceSeed:
    """Build the starter dataset anchored to ``base``, so today is never empty."""
    return WorkspaceSeed(
        leads=_seed_leads(base),
        tasks=_seed_tasks(base),
        emails=_seed_emails(base),
        events=_seed_events(base),
        suggestions=_seed_suggestions(),
    )


class WorkspaceStore(Protocol):
    """Read/write access to workspace entities."""

    def now(self) -> datetime: ...

    def tasks(self) -> list[Task]: ...

    def leads(self) -> list[Lead]: ...

    def lead(self, lead_id: str) -> Lead | None: ...

    def emails(self) -> list[EmailThread]: ...

    def events(self) -> list[CalendarEvent]: ...

    def suggestions(self) -> list[Suggestion]: ...

    def add_event(self, event: CalendarEvent) -> None: ...

    def mark_email_answered(self, email_id: str) -> bool: ...

    def complete_task(self, task_id: str) -> bool: ...


class InMemoryWorkspaceStore:
    """A seeded, in-process workspace.

    Not thread-safe by design: FastAPI serves this from a single event loop and
    every mutation is a whole-list replacement. Phase 2 moves this to Postgres,
    where concurrency becomes the database's problem.
    """

    def __init__(self, clock: Callable[[], datetime] = utcnow) -> None:
        self._clock = clock
        base = clock()
        self._tasks = _seed_tasks(base)
        self._leads = _seed_leads(base)
        self._emails = _seed_emails(base)
        self._events = _seed_events(base)
        self._suggestions = _seed_suggestions()

    def now(self) -> datetime:
        return self._clock()

    def tasks(self) -> list[Task]:
        return list(self._tasks)

    def leads(self) -> list[Lead]:
        return list(self._leads)

    def lead(self, lead_id: str) -> Lead | None:
        return next((lead for lead in self._leads if lead.id == lead_id), None)

    def emails(self) -> list[EmailThread]:
        return list(self._emails)

    def events(self) -> list[CalendarEvent]:
        return list(self._events)

    def suggestions(self) -> list[Suggestion]:
        return list(self._suggestions)

    def add_event(self, event: CalendarEvent) -> None:
        self._events = sorted([*self._events, event], key=lambda e: e.starts_at)

    def mark_email_answered(self, email_id: str) -> bool:
        found = False
        updated = []
        for thread in self._emails:
            if thread.id == email_id:
                found = True
                updated.append(thread.model_copy(update={"unread": False, "needs_response": False}))
            else:
                updated.append(thread)
        self._emails = updated
        return found

    def complete_task(self, task_id: str) -> bool:
        found = False
        updated = []
        for task in self._tasks:
            if task.id == task_id:
                found = True
                updated.append(task.model_copy(update={"status": TaskStatus.DONE}))
            else:
                updated.append(task)
        self._tasks = updated
        return found


# --------------------------------------------------------------------------
# Seed data
#
# Representative GTA residential brokerage activity. Replaced wholesale by the
# Phase 2 database; the shapes are the contract, the values are not.
# --------------------------------------------------------------------------


def _at(base: datetime, *, days: int = 0, hours: int = 0) -> datetime:
    return (base + timedelta(days=days, hours=hours)).replace(microsecond=0)


def _seed_tasks(base: datetime) -> list[Task]:
    midnight = base.replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        Task(
            id="tsk_001",
            title="Follow up with Priya Raman on the Yonge & Eglinton condo",
            due_at=_at(midnight, hours=10),
            priority=TaskPriority.HIGH,
            status=TaskStatus.TODO,
            lead_id="lead_001",
        ),
        Task(
            id="tsk_002",
            title="Send comparables package to the Chen family",
            due_at=_at(midnight, hours=13),
            priority=TaskPriority.HIGH,
            status=TaskStatus.IN_PROGRESS,
            lead_id="lead_002",
        ),
        Task(
            id="tsk_003",
            title="Confirm Saturday open house staging",
            due_at=_at(midnight, hours=16),
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.TODO,
        ),
        Task(
            id="tsk_004",
            title="Review conditional offer on 42 Maple Grove",
            due_at=_at(midnight, hours=17),
            priority=TaskPriority.HIGH,
            status=TaskStatus.TODO,
            lead_id="lead_004",
        ),
        Task(
            id="tsk_005",
            title="Renew MLS listing photos for 88 Harbour St",
            due_at=_at(midnight, days=1, hours=11),
            priority=TaskPriority.LOW,
            status=TaskStatus.TODO,
        ),
        Task(
            id="tsk_006",
            title="Post this week's market update to social",
            due_at=_at(midnight, days=-1, hours=9),
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.DONE,
        ),
    ]


def _seed_leads(base: datetime) -> list[Lead]:
    return [
        Lead(
            id="lead_001",
            name="Priya Raman",
            email="priya.raman@example.com",
            phone="+1-416-555-0142",
            stage=LeadStage.SHOWING,
            budget_min=850_000,
            budget_max=1_050_000,
            last_contact_at=_at(base, days=-1),
            score=92,
            notes="Wants a 2-bed near the Eglinton Crosstown. Pre-approved.",
        ),
        Lead(
            id="lead_002",
            name="Wei & Lin Chen",
            email="chen.family@example.com",
            phone="+1-647-555-0119",
            stage=LeadStage.QUALIFIED,
            budget_min=1_200_000,
            budget_max=1_600_000,
            last_contact_at=_at(base, days=-3),
            score=84,
            notes="Relocating from Vancouver in the spring. School catchment matters.",
        ),
        Lead(
            id="lead_003",
            name="Marcus Bell",
            email="m.bell@example.com",
            phone="+1-416-555-0177",
            stage=LeadStage.NEW,
            budget_min=600_000,
            budget_max=750_000,
            last_contact_at=_at(base, hours=-5),
            score=61,
            notes="First-time buyer, enquired through the Harbour St listing page.",
        ),
        Lead(
            id="lead_004",
            name="Dana Okafor",
            email="dana.okafor@example.com",
            phone="+1-905-555-0163",
            stage=LeadStage.OFFER,
            budget_min=950_000,
            budget_max=1_100_000,
            last_contact_at=_at(base, hours=-2),
            score=97,
            notes="Conditional offer in on 42 Maple Grove. Financing condition to Friday.",
        ),
        Lead(
            id="lead_005",
            name="Sofia Marchetti",
            email="sofia.m@example.com",
            phone="+1-416-555-0198",
            stage=LeadStage.CONTACTED,
            budget_min=700_000,
            budget_max=900_000,
            last_contact_at=_at(base, days=-9),
            score=44,
            notes="Went quiet after the first call. Worth one more touch.",
        ),
        Lead(
            id="lead_006",
            name="Tomas Nowak",
            email="t.nowak@example.com",
            phone="+1-647-555-0155",
            stage=LeadStage.CLOSED,
            budget_min=500_000,
            budget_max=650_000,
            last_contact_at=_at(base, days=-14),
            score=100,
            notes="Closed on the Danforth semi. Ask for a referral and a review.",
        ),
    ]


def _seed_emails(base: datetime) -> list[EmailThread]:
    return [
        EmailThread(
            id="eml_001",
            subject="Re: Showing this Thursday?",
            sender="Priya Raman",
            preview="Thursday after 6pm works for us. Is the unit still available?",
            received_at=_at(base, hours=-1),
            unread=True,
            needs_response=True,
            lead_id="lead_001",
        ),
        EmailThread(
            id="eml_002",
            subject="Financing condition — update",
            sender="Dana Okafor",
            preview="The lender needs one more document. Can we push to Friday?",
            received_at=_at(base, hours=-3),
            unread=True,
            needs_response=True,
            lead_id="lead_004",
        ),
        EmailThread(
            id="eml_003",
            subject="Comparables for Lawrence Park",
            sender="Wei Chen",
            preview="Could you send recent sales for the area we discussed?",
            received_at=_at(base, hours=-8),
            unread=True,
            needs_response=True,
            lead_id="lead_002",
        ),
        EmailThread(
            id="eml_004",
            subject="Open house sign delivery",
            sender="GTA Print Co.",
            preview="Your order ships Wednesday and arrives before the weekend.",
            received_at=_at(base, days=-1),
            unread=False,
            needs_response=False,
        ),
        EmailThread(
            id="eml_005",
            subject="Referral from Tomas Nowak",
            sender="Grace Adeyemi",
            preview="Tomas suggested I reach out about selling my Leslieville duplex.",
            received_at=_at(base, days=-1, hours=-4),
            unread=False,
            needs_response=True,
        ),
    ]


def _seed_events(base: datetime) -> list[CalendarEvent]:
    midnight = base.replace(hour=0, minute=0, second=0, microsecond=0)
    return sorted(
        [
            CalendarEvent(
                id="evt_001",
                title="Showing — 2201/155 Yonge St",
                starts_at=_at(midnight, hours=11),
                ends_at=_at(midnight, hours=12),
                location="155 Yonge St, Toronto",
                kind=EventKind.SHOWING,
                lead_id="lead_001",
            ),
            CalendarEvent(
                id="evt_002",
                title="Call — Chen family relocation planning",
                starts_at=_at(midnight, hours=14),
                ends_at=_at(midnight, hours=14) + timedelta(minutes=30),
                location="Phone",
                kind=EventKind.CALL,
                lead_id="lead_002",
            ),
            CalendarEvent(
                id="evt_003",
                title="Offer review — 42 Maple Grove",
                starts_at=_at(midnight, hours=17),
                ends_at=_at(midnight, hours=18),
                location="Office",
                kind=EventKind.MEETING,
                lead_id="lead_004",
            ),
            CalendarEvent(
                id="evt_004",
                title="Open house — 88 Harbour St",
                starts_at=_at(midnight, days=2, hours=13),
                ends_at=_at(midnight, days=2, hours=16),
                location="88 Harbour St, Toronto",
                kind=EventKind.OPEN_HOUSE,
            ),
        ],
        key=lambda e: e.starts_at,
    )


def _seed_suggestions() -> list[Suggestion]:
    return [
        Suggestion(
            id="sug_001",
            title="Dana's financing condition expires Friday",
            rationale="The offer on 42 Maple Grove is the largest open deal and the "
            "lender is waiting on one document.",
            impact=Impact.HIGH,
            prompt="Draft a short email to Dana Okafor confirming exactly which document "
            "the lender still needs and proposing a Friday morning deadline.",
        ),
        Suggestion(
            id="sug_002",
            title="Priya is ready to book a second showing",
            rationale="She replied within the hour and has a pre-approval on file. "
            "Score 92, currently at the showing stage.",
            impact=Impact.HIGH,
            prompt="Schedule a showing for Priya Raman on Thursday evening at "
            "155 Yonge St and draft the confirmation email.",
        ),
        Suggestion(
            id="sug_003",
            title="Sofia has gone quiet for nine days",
            rationale="Contacted stage, score 44 and falling. One more touch before "
            "she is written off.",
            impact=Impact.MEDIUM,
            prompt="Draft a low-pressure check-in email to Sofia Marchetti with two "
            "new listings in her budget.",
        ),
        Suggestion(
            id="sug_004",
            title="Ask Tomas for a referral and a review",
            rationale="Closed two weeks ago and has already sent one referral your way.",
            impact=Impact.MEDIUM,
            prompt="Draft a warm thank-you note to Tomas Nowak asking for a Google "
            "review and mentioning the referral he already sent.",
        ),
    ]
