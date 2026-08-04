"""Repositories. Each implements a protocol declared in ``runtime``."""

from __future__ import annotations

from backend.db.repositories.claims import (
    Claim,
    ClaimRepository,
    DecayPolicy,
    LegalBasis,
    Sensitivity,
    SourceType,
)
from backend.db.repositories.consent import (
    Channel,
    ConsentDecision,
    ConsentRepository,
    ConsentStatus,
)
from backend.db.repositories.runs import PostgresRunStore
from backend.db.repositories.workspace import PostgresWorkspaceStore

__all__ = [
    "Channel",
    "Claim",
    "ClaimRepository",
    "ConsentDecision",
    "ConsentRepository",
    "ConsentStatus",
    "DecayPolicy",
    "LegalBasis",
    "PostgresRunStore",
    "PostgresWorkspaceStore",
    "Sensitivity",
    "SourceType",
]
