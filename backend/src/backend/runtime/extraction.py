"""Turn a note into claims.

The capture wedge: an operator dictates or types what happened after a
showing, and the workspace remembers it — with provenance, so nothing is ever
presented as fact without a source.

Two rules make this trustworthy rather than merely plausible:

**Quote or it did not happen.** Every extracted claim must carry a verbatim
span from the source note. Claims whose quote is not in the text are dropped
before they reach the ledger. This removes most invention at negligible cost.

**Protected attributes are never extracted.** The model is told not to, and
:func:`guard_claim` refuses them at the storage boundary regardless. Inferring
national origin, religion or familial status from a note is a fair housing
exposure, and it is not worth a single feature.

Cost: extraction is the highest-volume LLM call in the product, so it routes to
``Settings.extraction_model`` — intended to be the cheapest model that passes
the eval bar, not the default chat model.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from backend.runtime.claims import (
    ClaimStore,
    DecayPolicy,
    LegalBasis,
    Sensitivity,
    SourceType,
)
from backend.runtime.config import Settings
from backend.runtime.logger import get_logger

__all__ = ["ExtractedClaim", "Extraction", "Extractor", "build_extractor"]

log = get_logger(__name__)

EXTRACTION_PROMPT = """\
You turn a real-estate agent's note into structured memory.

Extract only what the note actually says. For every claim you must supply
`quote`: a verbatim span copied from the note that supports it. If you cannot
quote it, do not claim it.

Use short snake_case predicates, reused across notes where possible:
  spouse_name, children_count, pet_name, employer, neighbourhood_interest,
  budget_note, timeline, preferred_contact_time, hobby, concern, milestone

Confidence:
  1.0  stated plainly as fact
  0.7  stated but hedged or second-hand
  0.4  implied

Never extract, infer or guess: ethnicity, national origin, religion, immigration
status, disability, health, age, or family composition as a protected
characteristic. Skip them entirely even if the note mentions them.

Also give a one-line summary and any concrete follow-ups the note implies.
"""


class ExtractedClaim(BaseModel):
    predicate: str = Field(max_length=100)
    value: str = Field(max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    quote: str = Field(description="Verbatim span from the note supporting this claim.")
    volatile: bool = Field(
        default=False,
        description="True if this is likely to stop being true within months.",
    )


class Extraction(BaseModel):
    summary: str = Field(max_length=500)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def grounded_claims(extraction: Extraction, note: str) -> tuple[list[ExtractedClaim], int]:
    """Keep only claims whose quote really appears in the note.

    Returns the survivors and how many were discarded, so ungrounded output is
    measurable rather than invisible.
    """
    haystack = _normalise(note)
    kept = [c for c in extraction.claims if c.quote.strip() and _normalise(c.quote) in haystack]
    return kept, len(extraction.claims) - len(kept)


class Extractor:
    """Extracts claims from notes and writes them to the ledger."""

    def __init__(self, agent: Agent[None, Extraction], claims: ClaimStore) -> None:
        self._agent = agent
        self._claims = claims

    async def capture(
        self, *, note: str, lead_id: str, source_ref: str | None = None
    ) -> tuple[Extraction, list[str], int]:
        """Extract from a note and persist the grounded claims.

        Returns the grounded extraction, the stored claim ids, and how many
        claims were discarded for lacking a verbatim quote.
        """
        result = await self._agent.run(note)
        extraction = result.output

        kept, dropped = grounded_claims(extraction, note)
        if dropped:
            log.warning("extraction.ungrounded_dropped", lead_id=lead_id, dropped=dropped)

        claim_ids = [
            self._claims.assert_claim(
                lead_id=lead_id,
                predicate=claim.predicate,
                object_value=claim.value,
                source_type=SourceType.CONVERSATION,
                confidence=claim.confidence,
                source_ref=source_ref,
                source_quote=claim.quote,
                sensitivity=Sensitivity.NORMAL,
                legal_basis=LegalBasis.LEGITIMATE_INTEREST,
                decay_policy=DecayPolicy.VOLATILE if claim.volatile else DecayPolicy.STATIC,
            )
            for claim in kept
        ]

        log.info(
            "extraction.captured",
            lead_id=lead_id,
            claims=len(claim_ids),
            dropped=dropped,
            chars=len(note),
        )
        return extraction.model_copy(update={"claims": kept}), claim_ids, dropped


def build_extractor(settings: Settings, claims: ClaimStore) -> Extractor:
    from backend.runtime.agent import resolve_model
    from backend.runtime.stub import STUB_MODEL_NAME, build_stub_extraction_model

    spec = settings.extraction_model or settings.default_model
    # The chat stub emits tool calls; extraction needs structured output, so it
    # gets its own offline model.
    model = (
        build_stub_extraction_model() if spec == STUB_MODEL_NAME else resolve_model(settings, spec)
    )
    agent: Agent[None, Extraction] = Agent(
        model=model,
        system_prompt=EXTRACTION_PROMPT,
        output_type=Extraction,
        name="extractor",
    )
    return Extractor(agent, claims)
