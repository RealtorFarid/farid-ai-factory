"""Database schema.

Three properties of this schema are load-bearing and cannot be retrofitted
later, so they exist before the first row:

1. **Tenancy.** Every business row carries ``org_id``. Adding it after data
   exists is a migration with no correct answer.
2. **Provenance.** A :class:`Claim` records where a fact came from, how
   confident we are, and under what legal basis. A fact without provenance is
   an unverifiable assertion, and back-filling it is impossible.
3. **Consent.** Recorded per person, per channel, per jurisdiction, before any
   outbound capability exists. Retrofitting consent is a legal event, not a
   migration.

Claims are append-only: corrections supersede rather than overwrite, so what
was believed on any past date is always reconstructable.

Deliberately absent: embeddings/pgvector. Nothing generates them yet, and an
unused index is a maintenance cost. Added with the capture pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = [
    "Base",
    "CalendarEventRow",
    "ClaimRow",
    "ConsentRow",
    "EmailThreadRow",
    "LeadRow",
    "OperatorRow",
    "OrganisationRow",
    "RunRow",
    "RunToolCallRow",
    "SuggestionRow",
    "TaskRow",
]


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[str]:
    return mapped_column(String(64), primary_key=True)


def _org_fk() -> Mapped[str]:
    return mapped_column(
        String(64), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True
    )


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---- Tenancy -------------------------------------------------------------


class OrganisationRow(Base):
    __tablename__ = "organisations"

    id: Mapped[str] = _pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _created()


class OperatorRow(Base):
    """A real estate professional. The human whose business this is."""

    __tablename__ = "operators"

    id: Mapped[str] = _pk()
    org_id: Mapped[str] = _org_fk()
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_operator_org_email"),)


# ---- Workspace -----------------------------------------------------------


class LeadRow(Base):
    """A person the operator has a relationship with, prospective or past."""

    __tablename__ = "leads"

    id: Mapped[str] = _pk()
    org_id: Mapped[str] = _org_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    budget_min: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    budget_max: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_contact_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 100", name="ck_lead_score_range"),
        Index("ix_lead_org_score", "org_id", "score"),
    )


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = _pk()
    org_id: Mapped[str] = _org_fk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _created()

    __table_args__ = (Index("ix_task_org_due", "org_id", "due_at"),)


class EmailThreadRow(Base):
    __tablename__ = "email_threads"

    id: Mapped[str] = _pk()
    org_id: Mapped[str] = _org_fk()
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(String(200), nullable=False)
    preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unread: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    needs_response: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lead_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _created()

    __table_args__ = (Index("ix_email_org_received", "org_id", "received_at"),)


class CalendarEventRow(Base):
    __tablename__ = "calendar_events"

    id: Mapped[str] = _pk()
    org_id: Mapped[str] = _org_fk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    lead_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _created()

    __table_args__ = (Index("ix_event_org_starts", "org_id", "starts_at"),)


class SuggestionRow(Base):
    __tablename__ = "suggestions"

    id: Mapped[str] = _pk()
    org_id: Mapped[str] = _org_fk()
    title: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created()


# ---- The Claim Ledger ----------------------------------------------------


class ClaimRow(Base):
    """One asserted fact about a person, with where it came from.

    Append-only. A correction inserts a new row and sets ``superseded_by`` on
    the old one, so the belief state at any past moment is reconstructable —
    which is what makes disputes answerable and evaluation possible.

    ``sensitivity = 'protected'`` marks attributes covered by fair housing law
    (national origin, religion, familial status, disability). Those rows must
    never reach a property, pricing, or lead-routing surface. The column exists
    now so the constraint can be enforced the day such a surface is built.
    """

    __tablename__ = "claims"

    id: Mapped[str] = _pk()
    org_id: Mapped[str] = _org_fk()
    lead_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The fact itself, as a triple: "Priya · spouse_name · Reza".
    predicate: Mapped[str] = mapped_column(String(100), nullable=False)
    object_value: Mapped[str] = mapped_column(Text, nullable=False)
    object_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Provenance. Nothing is stored as truth.
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Governance.
    legal_basis: Mapped[str] = mapped_column(
        String(32), nullable=False, default="legitimate_interest"
    )
    sensitivity: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="operator")

    # Lifecycle. Facts go stale; a stale fact stated confidently destroys trust.
    asserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decay_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="static")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    superseded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_claim_confidence"),
        CheckConstraint(
            "sensitivity IN ('normal', 'sensitive', 'protected')", name="ck_claim_sensitivity"
        ),
        CheckConstraint(
            "status IN ('active', 'contradicted', 'retracted', 'tombstoned')",
            name="ck_claim_status",
        ),
        Index("ix_claim_lead_predicate", "lead_id", "predicate"),
        Index("ix_claim_org_status", "org_id", "status"),
    )


# ---- The Consent Ledger --------------------------------------------------


class ConsentRow(Base):
    """Permission to contact a person on a channel, in a jurisdiction.

    Exists before any outbound capability does. CASL requires demonstrable
    express consent and TCPA damages are per-message, so "we'll add consent
    when we add SMS" is not a viable sequence.
    """

    __tablename__ = "consents"

    id: Mapped[str] = _pk()
    org_id: Mapped[str] = _org_fk()
    lead_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="granted")
    basis: Mapped[str] = mapped_column(String(32), nullable=False, default="express")
    jurisdiction: Mapped[str | None] = mapped_column(String(8), nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        CheckConstraint(
            "status IN ('granted', 'revoked', 'expired', 'never_asked')", name="ck_consent_status"
        ),
        UniqueConstraint("lead_id", "channel", name="uq_consent_lead_channel"),
    )


# ---- Runs ----------------------------------------------------------------


class RunRow(Base):
    """One agent conversation, including enough state to resume it later.

    ``messages_json`` and ``deferred_json`` are PydanticAI structures held as
    opaque JSON. They are serialised with that library's own type adapters and
    never queried — treating them as an internal format we store rather than a
    schema we own. A paused approval survives a restart because of these two
    columns.
    """

    __tablename__ = "runs"

    id: Mapped[str] = _pk()
    org_id: Mapped[str] = _org_fk()
    operator_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)

    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    messages_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    deferred_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_approvals: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (Index("ix_run_org_created", "org_id", "created_at"),)


class RunToolCallRow(Base):
    """The audit trail: what the assistant proposed, and what became of it."""

    __tablename__ = "run_tool_calls"

    id: Mapped[str] = _pk()
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = _created()

    __table_args__ = (
        UniqueConstraint("run_id", "tool_call_id", name="uq_tool_call_run_id"),
        CheckConstraint(
            "status IN ('proposed', 'executed', 'denied', 'failed')", name="ck_tool_call_status"
        ),
    )
