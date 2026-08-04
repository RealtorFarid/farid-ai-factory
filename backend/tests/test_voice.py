"""Voice capture: speak after a showing, get remembered facts."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from backend.api.app import create_app
from backend.runtime.claims import InMemoryClaimStore
from backend.runtime.config import Settings
from backend.runtime.extraction import Extraction, Extractor
from backend.runtime.transcription import (
    StubTranscriber,
    Transcript,
    TranscriptionError,
    _iso_639_1,
)
from tests.conftest import make_runtime

PERSIAN = "امروز با پریا ملاقات کردم. همسرش رضا هم آمد."


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    stub = settings.model_copy(update={"default_model": "stub", "max_prompt_chars": 20_000})
    with TestClient(create_app(settings=stub, runtime=make_runtime(stub))) as test_client:
        yield test_client


def post_voice(
    client: TestClient,
    *,
    lead_id: str = "lead_001",
    data: bytes = b"fake-audio-bytes",
    content_type: str = "audio/webm",
    filename: str = "note.webm",
):  # type: ignore[no-untyped-def]
    return client.post(
        "/v1/capture/voice",
        data={"lead_id": lead_id},
        files={"audio": (filename, data, content_type)},
    )


# ---- Language detection --------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("en", "en"),
        ("fa", "fa"),
        ("Persian", "fa"),
        ("farsi", "fa"),
        ("Spanish", "es"),
        ("english", "en"),
        ("", None),
        (None, None),
        (123, None),
    ],
)
def test_language_normalisation(value: object, expected: str | None) -> None:
    assert _iso_639_1(value) == expected


async def test_stub_transcriber_returns_persian() -> None:
    """The offline path exercises the multilingual case, not the easy one."""
    transcript = await StubTranscriber().transcribe(
        audio=b"x" * 32_000, filename="n.webm", content_type="audio/webm"
    )
    assert transcript.language == "fa"
    assert transcript.text
    assert transcript.duration_seconds and transcript.duration_seconds > 0


# ---- The endpoint --------------------------------------------------------


def test_voice_note_becomes_claims(client: TestClient) -> None:
    response = post_voice(client)
    assert response.status_code == 200
    body = response.json()

    assert body["transcript"], "the operator must see what was heard"
    assert body["language"] == "fa"
    assert body["claims"]
    # Grounding still applies to speech: every claim quotes the transcript.
    assert all(c["quote"] in body["transcript"] for c in body["claims"])

    listed = client.get("/v1/leads/lead_001/claims").json()
    assert len(listed) == len(body["claims"])


def test_voice_rejects_unknown_lead(client: TestClient) -> None:
    assert post_voice(client, lead_id="nope").status_code == 404


def test_voice_rejects_unsupported_format(client: TestClient) -> None:
    response = post_voice(client, content_type="application/pdf", filename="x.pdf")
    assert response.status_code == 415
    assert "Unsupported audio type" in response.json()["error"]["message"]


def test_voice_rejects_empty_recording(client: TestClient) -> None:
    assert post_voice(client, data=b"").status_code == 422


def test_voice_rejects_oversized_recording(settings: Settings) -> None:
    small = settings.model_copy(
        update={"default_model": "stub", "max_audio_bytes": 128, "max_prompt_chars": 20_000}
    )
    with TestClient(create_app(settings=small, runtime=make_runtime(small))) as client:
        response = post_voice(client, data=b"x" * 512)
    assert response.status_code == 413


def test_voice_reports_transcription_failure(settings: Settings) -> None:
    """A provider outage must be a clean 502, not a stack trace."""

    class Broken:
        async def transcribe(self, **_: object) -> Transcript:
            raise TranscriptionError("provider unavailable")

    stub = settings.model_copy(update={"default_model": "stub", "max_prompt_chars": 20_000})
    app = create_app(settings=stub, runtime=make_runtime(stub))
    app.state.transcriber = Broken()
    with TestClient(app) as client:
        response = post_voice(client)
    assert response.status_code == 502


def test_voice_rejects_silence(settings: Settings) -> None:
    class Silent:
        async def transcribe(self, **_: object) -> Transcript:
            return Transcript(text="   ", language=None, duration_seconds=0.4)

    stub = settings.model_copy(update={"default_model": "stub", "max_prompt_chars": 20_000})
    app = create_app(settings=stub, runtime=make_runtime(stub))
    app.state.transcriber = Silent()
    with TestClient(app) as client:
        response = post_voice(client)
    assert response.status_code == 422


# ---- Multilingual extraction ---------------------------------------------


async def test_claims_keep_the_note_language() -> None:
    """A Persian note must produce Persian values, not translated ones."""
    payload = {
        "summary": "ملاقات با پریا",
        "language": "fa",
        "claims": [
            {
                "predicate": "spouse_name",
                "value": "رضا",
                "confidence": 0.9,
                "quote": "همسرش رضا هم آمد",
            }
        ],
        "follow_ups": [],
    }

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        name = info.output_tools[0].name if info.output_tools else "final_result"
        return ModelResponse(parts=[ToolCallPart(name, json.dumps(payload))])

    store = InMemoryClaimStore()
    agent: Agent[None, Extraction] = Agent(
        model=FunctionModel(respond), output_type=Extraction, name="extractor"
    )
    extraction, ids, _ = await Extractor(agent, store).capture(
        note=PERSIAN, lead_id="lead_001", language="fa"
    )

    assert extraction.language == "fa"
    claim = store.for_lead("lead_001")[0]
    assert claim.id == ids[0]
    assert claim.object_value == "رضا"  # not transliterated, not translated
    assert claim.predicate == "spouse_name"  # keys stay English
    assert claim.object_data == {"language": "fa"}


async def test_transcriber_language_beats_the_model_guess() -> None:
    payload = {
        "summary": "s",
        "language": "en",
        "claims": [
            {"predicate": "x", "value": "y", "confidence": 0.8, "quote": "همسرش رضا هم آمد"}
        ],
        "follow_ups": [],
    }

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        name = info.output_tools[0].name if info.output_tools else "final_result"
        return ModelResponse(parts=[ToolCallPart(name, json.dumps(payload))])

    store = InMemoryClaimStore()
    agent: Agent[None, Extraction] = Agent(
        model=FunctionModel(respond), output_type=Extraction, name="extractor"
    )
    extraction, _, _ = await Extractor(agent, store).capture(
        note=PERSIAN, lead_id="lead_001", language="fa"
    )
    assert extraction.language == "fa"
