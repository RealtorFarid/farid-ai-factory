"""Postgres implementation of :class:`WorkspaceStore`.

A drop-in for ``InMemoryWorkspaceStore``: same protocol, same semantics, so the
service, tools and API above are unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select, update

from backend.db.engine import Database
from backend.db.models import (
    CalendarEventRow,
    EmailThreadRow,
    LeadRow,
    SuggestionRow,
    TaskRow,
)
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

__all__ = ["PostgresWorkspaceStore"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """Postgres returns aware datetimes; be defensive about drivers that don't."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class PostgresWorkspaceStore:
    def __init__(self, db: Database, org_id: str, clock: Callable[[], datetime] = _utcnow) -> None:
        self._db = db
        self._org_id = org_id
        self._clock = clock

    def now(self) -> datetime:
        return self._clock()

    # ---- Reads -----------------------------------------------------------

    def tasks(self) -> list[Task]:
        with self._db.session() as s:
            rows = s.scalars(
                select(TaskRow).where(TaskRow.org_id == self._org_id).order_by(TaskRow.due_at)
            ).all()
            return [
                Task(
                    id=r.id,
                    title=r.title,
                    due_at=_aware(r.due_at),
                    priority=TaskPriority(r.priority),
                    status=TaskStatus(r.status),
                    lead_id=r.lead_id,
                )
                for r in rows
            ]

    def leads(self) -> list[Lead]:
        with self._db.session() as s:
            rows = s.scalars(
                select(LeadRow).where(LeadRow.org_id == self._org_id).order_by(LeadRow.score.desc())
            ).all()
            return [self._to_lead(r) for r in rows]

    def lead(self, lead_id: str) -> Lead | None:
        with self._db.session() as s:
            row = s.scalar(
                select(LeadRow).where(LeadRow.id == lead_id, LeadRow.org_id == self._org_id)
            )
            return self._to_lead(row) if row else None

    def emails(self) -> list[EmailThread]:
        with self._db.session() as s:
            rows = s.scalars(
                select(EmailThreadRow)
                .where(EmailThreadRow.org_id == self._org_id)
                .order_by(EmailThreadRow.received_at.desc())
            ).all()
            return [
                EmailThread(
                    id=r.id,
                    subject=r.subject,
                    sender=r.sender,
                    preview=r.preview,
                    received_at=_aware(r.received_at),
                    unread=r.unread,
                    needs_response=r.needs_response,
                    lead_id=r.lead_id,
                )
                for r in rows
            ]

    def events(self) -> list[CalendarEvent]:
        with self._db.session() as s:
            rows = s.scalars(
                select(CalendarEventRow)
                .where(CalendarEventRow.org_id == self._org_id)
                .order_by(CalendarEventRow.starts_at)
            ).all()
            return [
                CalendarEvent(
                    id=r.id,
                    title=r.title,
                    starts_at=_aware(r.starts_at),
                    ends_at=_aware(r.ends_at),
                    location=r.location,
                    kind=EventKind(r.kind),
                    lead_id=r.lead_id,
                )
                for r in rows
            ]

    def suggestions(self) -> list[Suggestion]:
        with self._db.session() as s:
            rows = s.scalars(
                select(SuggestionRow).where(SuggestionRow.org_id == self._org_id)
            ).all()
            return [
                Suggestion(
                    id=r.id,
                    title=r.title,
                    rationale=r.rationale,
                    impact=Impact(r.impact),
                    prompt=r.prompt,
                )
                for r in rows
            ]

    # ---- Writes ----------------------------------------------------------

    def add_event(self, event: CalendarEvent) -> None:
        with self._db.session() as s:
            s.add(
                CalendarEventRow(
                    id=event.id,
                    org_id=self._org_id,
                    title=event.title,
                    starts_at=event.starts_at,
                    ends_at=event.ends_at,
                    location=event.location,
                    kind=event.kind.value,
                    lead_id=event.lead_id,
                )
            )

    def mark_email_answered(self, email_id: str) -> bool:
        with self._db.session() as s:
            updated = s.execute(
                update(EmailThreadRow)
                .where(
                    EmailThreadRow.id == email_id,
                    EmailThreadRow.org_id == self._org_id,
                )
                .values(unread=False, needs_response=False)
                .returning(EmailThreadRow.id)
            ).first()
            return updated is not None

    def complete_task(self, task_id: str) -> bool:
        with self._db.session() as s:
            updated = s.execute(
                update(TaskRow)
                .where(TaskRow.id == task_id, TaskRow.org_id == self._org_id)
                .values(status=TaskStatus.DONE.value)
                .returning(TaskRow.id)
            ).first()
            return updated is not None

    # ---- Mapping ---------------------------------------------------------

    @staticmethod
    def _to_lead(row: LeadRow) -> Lead:
        return Lead(
            id=row.id,
            name=row.name,
            email=row.email,
            phone=row.phone,
            stage=LeadStage(row.stage),
            budget_min=row.budget_min,
            budget_max=row.budget_max,
            last_contact_at=_aware(row.last_contact_at),
            score=row.score,
            notes=row.notes,
        )
