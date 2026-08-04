"""Postgres implementation of :class:`ClaimStore`.

Value types live in :mod:`backend.runtime.claims`; this module is only the
storage. Corrections supersede rather than overwrite, so the belief state on
any past date stays reconstructable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from backend.db.engine import Database
from backend.db.models import ClaimRow
from backend.runtime.claims import (
    Claim,
    DecayPolicy,
    LegalBasis,
    Sensitivity,
    SourceType,
    guard_claim,
)

__all__ = ["ClaimRepository"]


class ClaimRepository:
    def __init__(self, db: Database, org_id: str) -> None:
        self._db = db
        self._org_id = org_id

    def assert_claim(
        self,
        *,
        lead_id: str,
        predicate: str,
        object_value: str,
        source_type: SourceType,
        confidence: float = 1.0,
        source_ref: str | None = None,
        source_quote: str | None = None,
        sensitivity: Sensitivity = Sensitivity.NORMAL,
        legal_basis: LegalBasis = LegalBasis.LEGITIMATE_INTEREST,
        decay_policy: DecayPolicy = DecayPolicy.STATIC,
        object_data: dict[str, Any] | None = None,
    ) -> str:
        """Record a new claim.

        A protected attribute may never arrive by inference — that is a fair
        housing exposure, so it is rejected at the boundary rather than left to
        callers to remember.
        """
        guard_claim(sensitivity, source_type, predicate)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be between 0 and 1, got {confidence}")

        claim_id = f"clm_{uuid4().hex[:16]}"
        with self._db.session() as s:
            s.add(
                ClaimRow(
                    id=claim_id,
                    org_id=self._org_id,
                    lead_id=lead_id,
                    predicate=predicate,
                    object_value=object_value,
                    object_data=object_data,
                    confidence=confidence,
                    source_type=source_type.value,
                    source_ref=source_ref,
                    source_quote=source_quote,
                    sensitivity=sensitivity.value,
                    legal_basis=legal_basis.value,
                    decay_policy=decay_policy.value,
                    asserted_at=datetime.now(UTC),
                )
            )
        return claim_id

    def supersede(self, claim_id: str, replacement_id: str) -> bool:
        """Mark a claim as replaced. The original row is never mutated away."""
        with self._db.session() as s:
            row = s.get(ClaimRow, claim_id)
            if row is None or row.org_id != self._org_id:
                return False
            row.superseded_by = replacement_id
            row.status = "contradicted"
            return True

    def verify(self, claim_id: str, verified_by: str) -> bool:
        """A human confirmed this. Confidence becomes certainty."""
        with self._db.session() as s:
            row = s.get(ClaimRow, claim_id)
            if row is None or row.org_id != self._org_id:
                return False
            row.verified_at = datetime.now(UTC)
            row.verified_by = verified_by
            row.confidence = 1.0
            return True

    def retract(self, claim_id: str) -> bool:
        with self._db.session() as s:
            row = s.get(ClaimRow, claim_id)
            if row is None or row.org_id != self._org_id:
                return False
            row.status = "retracted"
            return True

    def for_lead(
        self,
        lead_id: str,
        *,
        min_confidence: float = 0.0,
        include_protected: bool = False,
    ) -> list[Claim]:
        """Active claims about one person.

        ``include_protected`` defaults to False so a caller must opt in
        deliberately — the safe default is not to hand protected attributes to
        code that did not ask for them.
        """
        with self._db.session() as s:
            query = (
                select(ClaimRow)
                .where(
                    ClaimRow.org_id == self._org_id,
                    ClaimRow.lead_id == lead_id,
                    ClaimRow.status == "active",
                    ClaimRow.confidence >= min_confidence,
                )
                .order_by(ClaimRow.confidence.desc(), ClaimRow.asserted_at.desc())
            )
            if not include_protected:
                query = query.where(ClaimRow.sensitivity != Sensitivity.PROTECTED.value)
            return [self._to_claim(r) for r in s.scalars(query).all()]

    @staticmethod
    def _to_claim(row: ClaimRow) -> Claim:
        return Claim(
            id=row.id,
            lead_id=row.lead_id,
            predicate=row.predicate,
            object_value=row.object_value,
            object_data=row.object_data,
            confidence=row.confidence,
            source_type=SourceType(row.source_type),
            source_ref=row.source_ref,
            source_quote=row.source_quote,
            sensitivity=Sensitivity(row.sensitivity),
            legal_basis=LegalBasis(row.legal_basis),
            decay_policy=DecayPolicy(row.decay_policy),
            asserted_at=row.asserted_at,
            verified_at=row.verified_at,
            status=row.status,
        )
