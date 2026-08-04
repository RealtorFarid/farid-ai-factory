"""First-run seeding.

Creates the default organisation and, if the workspace is empty, the same
starter dataset the in-memory store uses — so a fresh database produces the
same product experience as a fresh process.

Idempotent: safe to call on every boot.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from backend.db.engine import Database
from backend.db.models import (
    CalendarEventRow,
    EmailThreadRow,
    LeadRow,
    OperatorRow,
    OrganisationRow,
    SuggestionRow,
    TaskRow,
)
from backend.runtime.logger import get_logger
from backend.runtime.workspace.store import default_seed

__all__ = ["ensure_organisation", "seed_workspace"]

log = get_logger(__name__)


def ensure_organisation(db: Database, org_id: str, name: str = "Propilot") -> None:
    with db.session() as s:
        if s.get(OrganisationRow, org_id) is None:
            s.add(OrganisationRow(id=org_id, name=name))
            log.info("db.organisation_created", org_id=org_id)


def seed_workspace(
    db: Database, org_id: str, *, now: datetime | None = None, force: bool = False
) -> bool:
    """Populate the starter workspace if it is empty. Returns True if seeded."""
    base = now or datetime.now(UTC)
    ensure_organisation(db, org_id)

    with db.session() as s:
        existing = s.scalar(
            select(func.count()).select_from(LeadRow).where(LeadRow.org_id == org_id)
        )
        if existing and not force:
            return False

        seed = default_seed(base)

        operator_id = f"{org_id}_operator"
        if s.get(OperatorRow, operator_id) is None:
            s.add(
                OperatorRow(
                    id=operator_id,
                    org_id=org_id,
                    email="operator@propilot.local",
                    name="Operator",
                )
            )

        # Leads first: everything else references them.
        for lead in seed.leads:
            s.add(
                LeadRow(
                    id=lead.id,
                    org_id=org_id,
                    name=lead.name,
                    email=lead.email,
                    phone=lead.phone,
                    stage=lead.stage.value,
                    budget_min=lead.budget_min,
                    budget_max=lead.budget_max,
                    last_contact_at=lead.last_contact_at,
                    score=lead.score,
                    notes=lead.notes,
                )
            )
        s.flush()

        for task in seed.tasks:
            s.add(
                TaskRow(
                    id=task.id,
                    org_id=org_id,
                    title=task.title,
                    due_at=task.due_at,
                    priority=task.priority.value,
                    status=task.status.value,
                    lead_id=task.lead_id,
                )
            )
        for thread in seed.emails:
            s.add(
                EmailThreadRow(
                    id=thread.id,
                    org_id=org_id,
                    subject=thread.subject,
                    sender=thread.sender,
                    preview=thread.preview,
                    received_at=thread.received_at,
                    unread=thread.unread,
                    needs_response=thread.needs_response,
                    lead_id=thread.lead_id,
                )
            )
        for event in seed.events:
            s.add(
                CalendarEventRow(
                    id=event.id,
                    org_id=org_id,
                    title=event.title,
                    starts_at=event.starts_at,
                    ends_at=event.ends_at,
                    location=event.location,
                    kind=event.kind.value,
                    lead_id=event.lead_id,
                )
            )
        for suggestion in seed.suggestions:
            s.add(
                SuggestionRow(
                    id=suggestion.id,
                    org_id=org_id,
                    title=suggestion.title,
                    rationale=suggestion.rationale,
                    impact=suggestion.impact.value,
                    prompt=suggestion.prompt,
                )
            )

    log.info("db.workspace_seeded", org_id=org_id, leads=len(seed.leads))
    return True
