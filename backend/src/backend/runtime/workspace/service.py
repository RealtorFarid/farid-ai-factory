"""Workspace queries and mutations.

The single source of truth for "what does the user's day look like". Both the
agent tool registry and the REST API call into here, so an agent can never
quote a number the dashboard disagrees with.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from backend.runtime.workspace.models import (
    CalendarEvent,
    CalendarSummary,
    Dashboard,
    EmailSummary,
    EmailThread,
    EventKind,
    Lead,
    LeadStage,
    LeadSummary,
    Suggestion,
    Task,
    TaskStatus,
)
from backend.runtime.workspace.store import WorkspaceStore

__all__ = ["WorkspaceService"]

# A lead in an active stage that has not been touched in this long needs a nudge.
FOLLOW_UP_AFTER = timedelta(days=7)

_ACTIVE_STAGES = frozenset(
    {LeadStage.NEW, LeadStage.CONTACTED, LeadStage.QUALIFIED, LeadStage.SHOWING, LeadStage.OFFER}
)


class WorkspaceService:
    def __init__(self, store: WorkspaceStore) -> None:
        self._store = store

    # ---- Tasks -----------------------------------------------------------

    def todays_tasks(self, *, include_done: bool = False) -> list[Task]:
        """Tasks due today or overdue, most urgent first."""
        now = self._store.now()
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)

        tasks = [t for t in self._store.tasks() if t.due_at <= end_of_day]
        if not include_done:
            tasks = [t for t in tasks if t.status is not TaskStatus.DONE]

        priority_rank = {"high": 0, "medium": 1, "low": 2}
        return sorted(tasks, key=lambda t: (priority_rank[t.priority.value], t.due_at))

    def complete_task(self, task_id: str) -> bool:
        return self._store.complete_task(task_id)

    # ---- Leads -----------------------------------------------------------

    def lead_summary(self, *, hottest: int = 3) -> LeadSummary:
        leads = self._store.leads()
        now = self._store.now()
        week_ago = now - timedelta(days=7)

        active = [lead for lead in leads if lead.stage in _ACTIVE_STAGES]
        stale = [lead for lead in active if now - lead.last_contact_at > FOLLOW_UP_AFTER]

        return LeadSummary(
            total=len(leads),
            by_stage=dict(Counter(lead.stage.value for lead in leads)),
            new_this_week=sum(1 for lead in leads if lead.last_contact_at >= week_ago),
            needs_follow_up=len(stale),
            hottest=sorted(active, key=lambda lead: lead.score, reverse=True)[:hottest],
        )

    def leads(self) -> list[Lead]:
        return sorted(self._store.leads(), key=lambda lead: lead.score, reverse=True)

    def lead(self, lead_id: str) -> Lead | None:
        return self._store.lead(lead_id)

    # ---- Email -----------------------------------------------------------

    def email_summary(self, *, limit: int = 5) -> EmailSummary:
        threads = sorted(self._store.emails(), key=lambda t: t.received_at, reverse=True)
        return EmailSummary(
            unread=sum(1 for t in threads if t.unread),
            needs_response=sum(1 for t in threads if t.needs_response),
            threads=threads[:limit],
        )

    def mark_email_answered(self, email_id: str) -> bool:
        return self._store.mark_email_answered(email_id)

    # ---- Calendar --------------------------------------------------------

    def calendar_summary(self, *, days: int = 7) -> CalendarSummary:
        now = self._store.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        horizon = start_of_day + timedelta(days=days)
        end_of_day = start_of_day + timedelta(days=1)

        events = [e for e in self._store.events() if start_of_day <= e.starts_at < horizon]
        upcoming = [e for e in events if e.starts_at >= now]

        return CalendarSummary(
            today_count=sum(1 for e in events if e.starts_at < end_of_day),
            next_event=upcoming[0] if upcoming else None,
            events=events,
        )

    def schedule_event(
        self,
        *,
        title: str,
        starts_at: datetime,
        location: str,
        kind: EventKind = EventKind.SHOWING,
        lead_id: str | None = None,
        duration_minutes: int = 60,
    ) -> CalendarEvent:
        event = CalendarEvent(
            id=f"evt_{int(starts_at.timestamp())}",
            title=title,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=duration_minutes),
            location=location,
            kind=kind,
            lead_id=lead_id,
        )
        self._store.add_event(event)
        return event

    # ---- Suggestions -----------------------------------------------------

    def suggestions(self) -> list[Suggestion]:
        impact_rank = {"high": 0, "medium": 1, "low": 2}
        return sorted(self._store.suggestions(), key=lambda s: impact_rank[s.impact.value])

    # ---- Aggregate -------------------------------------------------------

    def dashboard(self) -> Dashboard:
        """Everything the home screen needs, in one round trip."""
        return Dashboard(
            generated_at=self._store.now(),
            tasks=self.todays_tasks(),
            leads=self.lead_summary(),
            emails=self.email_summary(),
            calendar=self.calendar_summary(),
            suggestions=self.suggestions(),
        )

    # ---- Rendering for agents -------------------------------------------

    def emails_needing_response(self) -> list[EmailThread]:
        return [t for t in self._store.emails() if t.needs_response]
