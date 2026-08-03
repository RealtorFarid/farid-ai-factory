"""Agent discovery, synchronous runs and SSE streaming."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.conftest import STUB_OUTPUT


def test_list_agents(client: TestClient) -> None:
    body = client.get("/v1/agents").json()
    assert body["default"] == "atlas"
    assert [a["name"] for a in body["agents"]] == ["atlas"]
    assert body["agents"][0]["description"]


def test_run_returns_output_and_usage(client: TestClient) -> None:
    response = client.post("/v1/agents/atlas/run", json={"prompt": "plan my week"})
    assert response.status_code == 200
    body = response.json()
    assert body["output"] == STUB_OUTPUT
    assert body["agent"] == "atlas"
    assert body["model"] == "test"
    assert body["duration_ms"] >= 0
    assert body["usage"]["output_tokens"] > 0
    assert body["usage"]["requests"] == 1
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_run_accepts_optional_session_id(client: TestClient) -> None:
    response = client.post("/v1/agents/atlas/run", json={"prompt": "hi", "session_id": "sess-1"})
    assert response.status_code == 200


def test_run_rejects_unknown_agent(client: TestClient) -> None:
    response = client.post("/v1/agents/ghost/run", json={"prompt": "hi"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "agent_not_found"


def test_run_rejects_empty_prompt(client: TestClient) -> None:
    response = client.post("/v1/agents/atlas/run", json={"prompt": ""})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_run_rejects_unknown_field(client: TestClient) -> None:
    response = client.post("/v1/agents/atlas/run", json={"prompt": "hi", "promt": "typo"})
    assert response.status_code == 422


def test_run_rejects_oversized_prompt(client: TestClient) -> None:
    response = client.post("/v1/agents/atlas/run", json={"prompt": "x" * 500})
    assert response.status_code == 413
    error = response.json()["error"]
    assert error["code"] == "prompt_too_long"
    assert "200" in error["message"]


def _parse_sse(raw: str) -> list[tuple[str, dict[str, object]]]:
    """Parse an SSE body into (event, data) pairs."""
    frames = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        event, data = "", "{}"
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = line.removeprefix("data: ")
        frames.append((event, json.loads(data)))
    return frames


def test_stream_emits_tokens_then_done(client: TestClient) -> None:
    with client.stream(
        "POST", "/v1/agents/atlas/stream", json={"prompt": "plan my week"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        frames = _parse_sse(response.read().decode())

    events = [name for name, _ in frames]
    assert events[-1] == "done"
    assert set(events[:-1]) == {"token"}

    streamed = "".join(str(data["delta"]) for name, data in frames if name == "token")
    done = frames[-1][1]
    assert streamed == STUB_OUTPUT
    assert done["output"] == STUB_OUTPUT
    assert done["agent"] == "atlas"
    assert isinstance(done["usage"], dict)


def test_stream_validates_before_streaming(client: TestClient) -> None:
    """Errors detectable up front must be real HTTP errors, not in-band frames."""
    assert client.post("/v1/agents/ghost/stream", json={"prompt": "hi"}).status_code == 404
    assert client.post("/v1/agents/atlas/stream", json={"prompt": "x" * 500}).status_code == 413
