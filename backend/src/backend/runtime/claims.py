"""Claim types and storage protocol.

The value types live here rather than in the database package so the runtime
can talk about claims without depending on Postgres — the same split already
used for the workspace.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

__all__ = [
    "Claim",
    "ClaimStore",
    "DecayPolicy",
    "InMemoryClaimStore",
    "LegalBasis",
    "Sensitivity",
    "SourceType",
]


class SourceType(StrEnum):
    CONVERSATION = "conversation"
    OPERATOR = "operator"
    CLIENT = "client"
    IMPORT = "import"
    PUBLIC = "public"
    INFERENCE = "inference"


class Sensitivity(StrEnum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"
    #: Fair-housing protected: national origin, religion, familial status,
    #: disability, age. Never model-inferred; never exposed to property,
    #: pricing or routing surfaces.
    PROTECTED = "protected"


class LegalBasis(StrEnum):
    CONSENT = "consent"
    CONTRACT = "contract"
    LEGITIMATE_INTEREST = "legitimate_interest"


class DecayPolicy(StrEnum):
    STATIC = "static"
    SLOW = "slow"
    VOLATILE = "volatile"


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    lead_id: str
    predicate: str
    object_value: str
    confidence: float
    source_type: SourceType
    source_ref: str | None
    source_quote: str | None
    sensitivity: Sensitivity
    legal_basis: LegalBasis
    decay_policy: DecayPolicy
    asserted_at: datetime
    verified_at: datetime | None
    status: str
    object_data: dict[str, Any] | None = None


class ClaimStore(Protocol):
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
    ) -> str: ...

    def supersede(self, claim_id: str, replacement_id: str) -> bool: ...

    def verify(self, claim_id: str, verified_by: str) -> bool: ...

    def retract(self, claim_id: str) -> bool: ...

    def for_lead(
        self, lead_id: str, *, min_confidence: float = 0.0, include_protected: bool = False
    ) -> list[Claim]: ...


def guard_claim(sensitivity: Sensitivity, source_type: SourceType, predicate: str) -> None:
    """Reject claims no implementation may accept.

    A protected attribute arriving by inference is a fair housing exposure, so
    it is refused at the boundary rather than left to each caller to remember.
    """
    if sensitivity is Sensitivity.PROTECTED and source_type is SourceType.INFERENCE:
        raise ValueError(
            f"protected attributes must be declared, never inferred (predicate={predicate!r})"
        )


class InMemoryClaimStore:
    """Non-durable claim store, for tests and the keyless demo."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}

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
        guard_claim(sensitivity, source_type, predicate)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be between 0 and 1, got {confidence}")

        claim_id = f"clm_{uuid4().hex[:16]}"
        self._claims[claim_id] = Claim(
            id=claim_id,
            lead_id=lead_id,
            predicate=predicate,
            object_value=object_value,
            object_data=object_data,
            confidence=confidence,
            source_type=source_type,
            source_ref=source_ref,
            source_quote=source_quote,
            sensitivity=sensitivity,
            legal_basis=legal_basis,
            decay_policy=decay_policy,
            asserted_at=datetime.now(UTC),
            verified_at=None,
            status="active",
        )
        return claim_id

    def _replace(self, claim_id: str, **changes: Any) -> bool:
        existing = self._claims.get(claim_id)
        if existing is None:
            return False
        self._claims[claim_id] = replace_claim(existing, **changes)
        return True

    def supersede(self, claim_id: str, replacement_id: str) -> bool:
        return self._replace(claim_id, status="contradicted")

    def verify(self, claim_id: str, verified_by: str) -> bool:
        return self._replace(claim_id, verified_at=datetime.now(UTC), confidence=1.0)

    def retract(self, claim_id: str) -> bool:
        return self._replace(claim_id, status="retracted")

    def for_lead(
        self, lead_id: str, *, min_confidence: float = 0.0, include_protected: bool = False
    ) -> list[Claim]:
        found = [
            c
            for c in self._claims.values()
            if c.lead_id == lead_id and c.status == "active" and c.confidence >= min_confidence
        ]
        if not include_protected:
            found = [c for c in found if c.sensitivity is not Sensitivity.PROTECTED]
        return sorted(found, key=lambda c: (c.confidence, c.asserted_at), reverse=True)

    def __iter__(self) -> Iterator[Claim]:
        return iter(self._claims.values())

    def __len__(self) -> int:
        return len(self._claims)


def replace_claim(claim: Claim, **changes: Any) -> Claim:
    data = {f: getattr(claim, f) for f in Claim.__slots__}
    data.update(changes)
    return Claim(**data)
