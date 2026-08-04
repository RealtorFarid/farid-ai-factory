"""Capture: turn a note into remembered facts.

The product wedge. An operator finishes a showing, says what happened, and the
workspace remembers it — with a quote behind every fact, so nothing is ever
shown as certain without a source.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from backend.api.deps import ClaimsDep, ExtractorDep, SettingsDep, TranscriberDep, WorkspaceDep
from backend.api.schemas import ErrorResponse
from backend.runtime.claims import Claim
from backend.runtime.transcription import (
    SUPPORTED_AUDIO,
    TranscriptionError,
)

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
    #: What the operator actually said, so they can check the machine heard right.
    transcript: str | None = None
    language: str | None = None
    duration_seconds: float | None = None
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
        language=extraction.language,
        follow_ups=extraction.follow_ups,
        claims=[_to_info(stored[cid]) for cid in claim_ids if cid in stored],
        discarded=discarded,
    )


@router.post(
    "/capture/voice",
    response_model=CaptureResponse,
    responses={
        **_ERRORS,
        status.HTTP_413_CONTENT_TOO_LARGE: {
            "model": ErrorResponse,
            "description": "Recording too large",
        },
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
            "model": ErrorResponse,
            "description": "Unsupported audio format",
        },
    },
    summary="Speak a note; it becomes remembered facts",
)
async def capture_voice(
    extractor: ExtractorDep,
    claims: ClaimsDep,
    workspace: WorkspaceDep,
    transcriber: TranscriberDep,
    settings: SettingsDep,
    lead_id: str = Form(...),
    audio: UploadFile = File(...),
) -> CaptureResponse:
    """Record after a showing and let the workspace do the writing.

    The transcript is returned alongside the claims so the operator can see
    what was heard — a mis-heard name is obvious in the transcript and
    invisible in a summary.
    """
    if workspace.lead(lead_id) is None:
        raise HTTPException(status_code=404, detail=f"No lead with id {lead_id!r}.")

    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    if content_type not in SUPPORTED_AUDIO:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio type {content_type!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_AUDIO))}.",
        )

    payload = await audio.read()
    if not payload:
        raise HTTPException(status_code=422, detail="The recording was empty.")
    if len(payload) > settings.max_audio_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Recording is {len(payload)} bytes; limit is {settings.max_audio_bytes}.",
        )

    filename = audio.filename or f"note.{SUPPORTED_AUDIO[content_type]}"
    try:
        transcript = await transcriber.transcribe(
            audio=payload, filename=filename, content_type=content_type
        )
    except TranscriptionError as exc:
        raise HTTPException(status_code=502, detail=f"Could not transcribe: {exc}") from exc

    # Normalise here rather than trusting every transcriber to do it: a
    # whitespace-only result is silence, not a note.
    spoken = transcript.text.strip()
    if not spoken:
        raise HTTPException(status_code=422, detail="Nothing was said in that recording.")

    extraction, claim_ids, discarded = await extractor.capture(
        note=spoken, lead_id=lead_id, source_ref="voice", language=transcript.language
    )
    stored = {c.id: c for c in claims.for_lead(lead_id)}

    return CaptureResponse(
        lead_id=lead_id,
        summary=extraction.summary,
        transcript=spoken,
        language=extraction.language or transcript.language,
        duration_seconds=transcript.duration_seconds,
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
