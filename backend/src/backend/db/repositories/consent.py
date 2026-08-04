"""The Consent Ledger — may we contact this person, on this channel.

Exists before any outbound capability. CASL requires demonstrable express
consent and TCPA damages run per message, so "add consent when we add SMS" is
not a viable order of work: by then there is contact history with no record of
permission behind it.

:meth:`ConsentRepository.may_contact` is the check every future send must pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import select

from backend.db.engine import Database
from backend.db.models import ConsentRow

__all__ = ["Channel", "ConsentDecision", "ConsentRepository", "ConsentStatus"]


class Channel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    VOICE = "voice"
    WHATSAPP = "whatsapp"
    POST = "post"


class ConsentStatus(StrEnum):
    GRANTED = "granted"
    REVOKED = "revoked"
    EXPIRED = "expired"
    NEVER_ASKED = "never_asked"


@dataclass(frozen=True, slots=True)
class ConsentDecision:
    """The answer, and the reason — so a refusal can be explained and audited."""

    allowed: bool
    status: ConsentStatus
    reason: str
    basis: str | None = None


class ConsentRepository:
    def __init__(self, db: Database, org_id: str) -> None:
        self._db = db
        self._org_id = org_id

    def grant(
        self,
        *,
        lead_id: str,
        channel: Channel,
        basis: str = "express",
        jurisdiction: str | None = None,
        evidence: str | None = None,
        expires_at: datetime | None = None,
    ) -> str:
        """Record permission. Evidence is what makes it defensible later."""
        now = datetime.now(UTC)
        with self._db.session() as s:
            row = s.scalar(
                select(ConsentRow).where(
                    ConsentRow.lead_id == lead_id, ConsentRow.channel == channel.value
                )
            )
            if row is None:
                row = ConsentRow(
                    id=f"con_{uuid4().hex[:16]}",
                    org_id=self._org_id,
                    lead_id=lead_id,
                    channel=channel.value,
                )
                s.add(row)
            row.status = ConsentStatus.GRANTED.value
            row.basis = basis
            row.jurisdiction = jurisdiction
            row.evidence = evidence
            row.granted_at = now
            row.revoked_at = None
            row.expires_at = expires_at
            return row.id

    def revoke(self, *, lead_id: str, channel: Channel) -> bool:
        """Withdrawal must be immediate and must win over any prior grant."""
        with self._db.session() as s:
            row = s.scalar(
                select(ConsentRow).where(
                    ConsentRow.org_id == self._org_id,
                    ConsentRow.lead_id == lead_id,
                    ConsentRow.channel == channel.value,
                )
            )
            if row is None:
                return False
            row.status = ConsentStatus.REVOKED.value
            row.revoked_at = datetime.now(UTC)
            return True

    def may_contact(
        self, *, lead_id: str, channel: Channel, now: datetime | None = None
    ) -> ConsentDecision:
        """The gate every outbound message must pass.

        Absence of a record is *not* permission — an unknown contact is a
        refusal, because silence is never consent.
        """
        moment = now or datetime.now(UTC)
        with self._db.session() as s:
            row = s.scalar(
                select(ConsentRow).where(
                    ConsentRow.org_id == self._org_id,
                    ConsentRow.lead_id == lead_id,
                    ConsentRow.channel == channel.value,
                )
            )

        if row is None:
            return ConsentDecision(
                allowed=False,
                status=ConsentStatus.NEVER_ASKED,
                reason=f"No consent record for {channel.value}.",
            )
        if row.status == ConsentStatus.REVOKED.value:
            return ConsentDecision(
                allowed=False, status=ConsentStatus.REVOKED, reason="Consent was withdrawn."
            )
        if row.expires_at is not None:
            expiry = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
            if expiry <= moment:
                return ConsentDecision(
                    allowed=False, status=ConsentStatus.EXPIRED, reason="Consent has expired."
                )
        if row.status != ConsentStatus.GRANTED.value:
            return ConsentDecision(
                allowed=False,
                status=ConsentStatus(row.status),
                reason=f"Consent status is {row.status}.",
            )
        return ConsentDecision(
            allowed=True,
            status=ConsentStatus.GRANTED,
            reason="Consent on file.",
            basis=row.basis,
        )
