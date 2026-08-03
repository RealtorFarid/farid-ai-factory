"""Agent discovery, runs, and the event stream."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import STUB_OUTPUT
from tests.sse import parse_sse


def test_list_agents(client: TestClient) -> None:
    body = client.get("/v1/agents").json()
    assert body["default"] == "atlas"
    assert [a["name"] for a in body["agents"]] == ["atlas"]
    assert body["agents"][0]["description"]


def test_list_tools_exposes_the_approval_policy(client: TestClient) -> None:
    tools = client.get("/v1/agents/tools").json()["tools"]
    by_name = {t["name"]: t for t in tools}

    assert by_name["summarize_leads"]["requires_approval"] is False
    assert by_name["send_email"]["requires_approval"] is True
    assert by_name["schedule_showing"]["requires_approval"] is True
    assert by_name["send_email"]["category"] == "email"
    assert all(t["description"] for t in tools)


def test_run_returns_a_completed_run(client: TestClient) -> None:
    response = client.post("/v1/agents/atlas/run", json={"prompt": "plan my week"})
    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "completed"
    assert body["output"] == STUB_OUTPUT
    assert body["agent"] == "atlas"
    assert body["model"] == "test"
    assert body["id"].startswith("run_")
    assert body["duration_ms"] >= 0
    assert body["usage"]["requests"] == 1
    assert body["pending_approvals"] == []
    assert response.headers["X-Request-ID"]


def test_run_records_the_session_id(client: TestClient) -> None:
    response = client.post("/v1/agents/atlas/run", json={"prompt": "hi", "session_id": "sess-1"})
    assert response.status_code == 200
    assert response.json()["session_id"] == "sess-1"


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


def test_stream_emits_started_tokens_and_completed(client: TestClient) -> None:
    with client.stream(
        "POST", "/v1/agents/atlas/stream", json={"prompt": "plan my week"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["X-Run-Id"].startswith("run_")
        frames = parse_sse(response.read().decode())

    events = [name for name, _ in frames]
    assert events[0] == "run.started"
    assert events[-1] == "run.completed"
    assert "run.token" in events

    streamed = "".join(str(data["data"]["delta"]) for name, data in frames if name == "run.token")
    assert streamed == STUB_OUTPUT
    assert frames[-1][1]["data"]["output"] == STUB_OUTPUT


def test_stream_validates_before_streaming(client: TestClient) -> None:
    """Errors detectable up front must be real HTTP errors, not in-band frames."""
    assert client.post("/v1/agents/ghost/stream", json={"prompt": "hi"}).status_code == 404
    assert client.post("/v1/agents/atlas/stream", json={"prompt": "x" * 500}).status_code == 413
