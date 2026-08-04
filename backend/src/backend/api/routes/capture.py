"""Capture: turn a note into remembered facts.

The product wedge. An operator finishes a showing, says what happened, and the
workspace remembers it — with a quote behind every fact, so nothing is ever
shown as certain without a source.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from backend.api.deps import ClaimsDep, ExtractorDep, WorkspaceDep
from backend.api.schemas import ErrorResponse
from backend.runtime.claims import Claim

router = APIRouter(prefix="/v1", tags=["capture"])

_ERRORS: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorResponse, "description": "Unknown lead"},
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaptureRequest(StrictModel):
    lead_id: str
    note: str = Field(
        min_length=1,
        max_length=20_000,
        description="What happened, in the operator's own words.",
        examples=["Met Priya at the Yonge showing. Her husband Reza came too."],
    )
    source_ref: str | None = Field(default=None, max_length=200)


class ClaimInfo(StrictModel):
    id: str
    predicate: str
    value: str
    confidence: float
    quote: str | None
    source_type: str
    asserted_at: str
    verified_at: str | None


class CaptureResponse(StrictModel):
    lead_id: str
    summary: str
    follow_ups: list[str]
    claims: list[ClaimInfo]
    #: Claims the model produced that could not be quoted from the note, and
    #: were therefore discarded rather than stored.
    discarded: int


@router.post(
    "/capture",
    response_model=CaptureResponse,
    responses=_ERRORS,
    summary="Turn a note into remembered facts",
)
async def capture(
    body: CaptureRequest,
    extractor: ExtractorDep,
    claims: ClaimsDep,
    workspace: WorkspaceDep,
) -> CaptureResponse:
    if workspace.lead(body.lead_id) is None:
        raise HTTPException(status_code=404, detail=f"No lead with id {body.lead_id!r}.")

    extraction, claim_ids, discarded = await extractor.capture(
        note=body.note, lead_id=body.lead_id, source_ref=body.source_ref
    )
    stored = {c.id: c for c in claims.for_lead(body.lead_id)}

    return CaptureResponse(
        lead_id=body.lead_id,
        summary=extraction.summary,
        follow_ups=extraction.follow_ups,
        claims=[_to_info(stored[cid]) for cid in claim_ids if cid in stored],
        discarded=discarded,
    )


@router.get(
    "/leads/{lead_id}/claims",
    response_model=list[ClaimInfo],
    responses=_ERRORS,
    summary="What we remember about a person",
)
def lead_claims(
    lead_id: str,
    claims: ClaimsDep,
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
) -> list[ClaimInfo]:
    """Protected attributes are never included here."""
    return [_to_info(c) for c in claims.for_lead(lead_id, min_confidence=min_confidence)]


def _to_info(claim: Claim) -> ClaimInfo:
    return ClaimInfo(
        id=claim.id,
        predicate=claim.predicate,
        value=claim.object_value,
        confidence=claim.confidence,
        quote=claim.source_quote,
        source_type=claim.source_type.value,
        asserted_at=claim.asserted_at.isoformat(),
        verified_at=claim.verified_at.isoformat() if claim.verified_at else None,
    )
