"""Capture: notes become claims, with a quote behind every one."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from backend.api.app import create_app
from backend.runtime.claims import InMemoryClaimStore, Sensitivity, SourceType
from backend.runtime.config import Settings
from backend.runtime.extraction import (
    ExtractedClaim,
    Extraction,
    Extractor,
    grounded_claims,
)
from tests.conftest import make_runtime

NOTE = (
    "Met Priya at the Yonge showing. Her husband Reza came too. They want to move before September."
)


def extraction_model(payload: dict[str, object]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        name = info.output_tools[0].name if info.output_tools else "final_result"
        return ModelResponse(parts=[ToolCallPart(name, json.dumps(payload))])

    return FunctionModel(respond)


def build_extractor(payload: dict[str, object]) -> tuple[Extractor, InMemoryClaimStore]:
    store = InMemoryClaimStore()
    agent: Agent[None, Extraction] = Agent(
        model=extraction_model(payload), output_type=Extraction, name="extractor"
    )
    return Extractor(agent, store), store


# ---- Grounding -----------------------------------------------------------


def test_grounding_keeps_quoted_claims_and_drops_the_rest() -> None:
    extraction = Extraction(
        summary="s",
        claims=[
            ExtractedClaim(
                predicate="spouse_name", value="Reza", confidence=0.9, quote="husband Reza"
            ),
            ExtractedClaim(
                predicate="employer", value="Shopify", confidence=0.9, quote="works at Shopify"
            ),
        ],
    )
    kept, dropped = grounded_claims(extraction, NOTE)
    assert [c.predicate for c in kept] == ["spouse_name"]
    assert dropped == 1


def test_grounding_ignores_whitespace_and_case() -> None:
    extraction = Extraction(
        summary="s",
        claims=[
            ExtractedClaim(predicate="x", value="y", confidence=1.0, quote="  HUSBAND\n  Reza  ")
        ],
    )
    kept, dropped = grounded_claims(extraction, NOTE)
    assert len(kept) == 1
    assert dropped == 0


async def test_ungrounded_claims_never_reach_the_ledger() -> None:
    """The model inventing a fact must not be able to persist it."""
    extractor, store = build_extractor(
        {
            "summary": "Showing went well.",
            "claims": [
                {
                    "predicate": "spouse_name",
                    "value": "Reza",
                    "confidence": 0.9,
                    "quote": "husband Reza",
                },
                {
                    "predicate": "income",
                    "value": "$400k",
                    "confidence": 0.9,
                    "quote": "they earn four hundred thousand",
                },
            ],
            "follow_ups": [],
        }
    )
    extraction, ids, dropped = await extractor.capture(note=NOTE, lead_id="lead_001")

    assert dropped == 1
    assert len(ids) == 1
    assert [c.predicate for c in extraction.claims] == ["spouse_name"]
    assert [c.predicate for c in store.for_lead("lead_001")] == ["spouse_name"]


async def test_captured_claims_carry_provenance() -> None:
    extractor, store = build_extractor(
        {
            "summary": "s",
            "claims": [
                {
                    "predicate": "timeline",
                    "value": "before September",
                    "confidence": 0.7,
                    "quote": "move before September",
                    "volatile": True,
                }
            ],
            "follow_ups": ["Confirm the September deadline."],
        }
    )
    _, ids, _ = await extractor.capture(note=NOTE, lead_id="lead_001", source_ref="memo_9")

    claim = store.for_lead("lead_001")[0]
    assert claim.id == ids[0]
    assert claim.source_type is SourceType.CONVERSATION
    assert claim.source_quote == "move before September"
    assert claim.source_ref == "memo_9"
    assert claim.confidence == 0.7
    assert claim.decay_policy.value == "volatile"


# ---- The in-memory store contract ----------------------------------------


def test_protected_claims_cannot_be_inferred() -> None:
    store = InMemoryClaimStore()
    with pytest.raises(ValueError, match="declared, never inferred"):
        store.assert_claim(
            lead_id="lead_001",
            predicate="religion",
            object_value="Muslim",
            source_type=SourceType.INFERENCE,
            sensitivity=Sensitivity.PROTECTED,
        )


def test_protected_claims_are_withheld_by_default() -> None:
    store = InMemoryClaimStore()
    store.assert_claim(
        lead_id="lead_001",
        predicate="children_count",
        object_value="2",
        source_type=SourceType.CLIENT,
        sensitivity=Sensitivity.PROTECTED,
    )
    assert store.for_lead("lead_001") == []
    assert len(store.for_lead("lead_001", include_protected=True)) == 1


def test_retract_and_verify() -> None:
    store = InMemoryClaimStore()
    claim_id = store.assert_claim(
        lead_id="lead_001",
        predicate="pet_name",
        object_value="Mochi",
        source_type=SourceType.CONVERSATION,
        confidence=0.5,
    )
    assert store.verify(claim_id, "operator_1") is True
    assert store.for_lead("lead_001")[0].confidence == 1.0
    assert store.retract(claim_id) is True
    assert store.for_lead("lead_001") == []
    assert store.verify("nope", "x") is False


# ---- API -----------------------------------------------------------------


@pytest.fixture
def capture_client(settings: Settings) -> Iterator[TestClient]:
    stub = settings.model_copy(update={"default_model": "stub", "max_prompt_chars": 20_000})
    with TestClient(create_app(settings=stub, runtime=make_runtime(stub))) as client:
        yield client


def test_capture_endpoint_stores_and_returns_claims(capture_client: TestClient) -> None:
    response = capture_client.post(
        "/v1/capture", json={"lead_id": "lead_001", "note": NOTE, "source_ref": "memo_1"}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["lead_id"] == "lead_001"
    assert body["summary"]
    assert body["claims"]
    assert all(c["quote"] for c in body["claims"]), "every claim must carry a quote"
    assert all(c["quote"] in NOTE for c in body["claims"])

    listed = capture_client.get("/v1/leads/lead_001/claims").json()
    assert len(listed) == len(body["claims"])


def test_capture_rejects_unknown_lead(capture_client: TestClient) -> None:
    response = capture_client.post("/v1/capture", json={"lead_id": "nope", "note": NOTE})
    assert response.status_code == 404


def test_capture_validates_input(capture_client: TestClient) -> None:
    assert (
        capture_client.post("/v1/capture", json={"lead_id": "lead_001", "note": ""}).status_code
        == 422
    )
    assert (
        capture_client.post(
            "/v1/capture", json={"lead_id": "lead_001", "note": "x", "nope": 1}
        ).status_code
        == 422
    )


def test_claims_endpoint_filters_by_confidence(capture_client: TestClient) -> None:
    capture_client.post("/v1/capture", json={"lead_id": "lead_001", "note": NOTE})
    high = capture_client.get("/v1/leads/lead_001/claims?min_confidence=0.95").json()
    assert high == []  # the stub asserts at 0.7
