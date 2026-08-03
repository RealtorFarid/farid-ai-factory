"""Failure modes end-to-end: agent timeouts and mid-stream errors.

These are the branches that only execute when something is already going
wrong, so they get explicit coverage rather than relying on the happy path.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.runtime.agent import AgentRegistry, AgentSpec
from backend.runtime.config import Settings
from tests.conftest import make_runtime
from tests.sse import parse_sse

# ---- Stub agents ---------------------------------------------------------


class _SlowStream:
    async def __aenter__(self) -> AsyncIterator[Any]:
        await asyncio.sleep(10)
        raise AssertionError("should not be reached")

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _SlowAgent:
    """Never finishes within a sane timeout."""

    def run_stream_events(self, *args: object, **kwargs: object) -> _SlowStream:
        return _SlowStream()


class _BrokenStream:
    async def __aenter__(self) -> AsyncIterator[Any]:
        raise RuntimeError("upstream model exploded")

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _BrokenAgent:
    def run_stream_events(self, *args: object, **kwargs: object) -> _BrokenStream:
        return _BrokenStream()


def _client(agent: object, timeout_seconds: float = 0.05) -> TestClient:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        log_level="CRITICAL",
        openai_api_key="sk-test",
        default_model="test",
        agent_timeout_seconds=timeout_seconds,
        max_prompt_chars=200,
    )
    registry = AgentRegistry()
    registry.register(AgentSpec(name="atlas", description="d", model="test", agent=agent))  # type: ignore[arg-type]
    runtime = make_runtime(settings, agents=registry)
    return TestClient(create_app(settings=settings, runtime=runtime))


# ---- Tests ---------------------------------------------------------------


def test_run_timeout_is_recorded_on_the_run() -> None:
    """A timeout is a run outcome, not an HTTP error: the run id stays useful."""
    with _client(_SlowAgent()) as client:
        response = client.post("/v1/agents/atlas/run", json={"prompt": "hi"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "agent_timeout"
    assert "0.05" in body["error"]


def test_stream_timeout_is_reported_in_band() -> None:
    with (
        _client(_SlowAgent()) as client,
        client.stream("POST", "/v1/agents/atlas/stream", json={"prompt": "hi"}) as response,
    ):
        assert response.status_code == 200
        frames = parse_sse(response.read().decode())

    names = [name for name, _ in frames]
    assert names[0] == "run.started"
    assert names[-1] == "run.failed"
    assert frames[-1][1]["data"]["code"] == "agent_timeout"


def test_stream_internal_error_does_not_leak_details() -> None:
    with (
        _client(_BrokenAgent(), timeout_seconds=5) as client,
        client.stream("POST", "/v1/agents/atlas/stream", json={"prompt": "hi"}) as response,
    ):
        assert response.status_code == 200
        frames = parse_sse(response.read().decode())

    assert [name for name, _ in frames][-1] == "run.failed"
    payload = frames[-1][1]["data"]
    assert payload["code"] == "internal_error"
    assert "upstream model exploded" not in payload["message"]


def test_failed_run_is_still_retrievable() -> None:
    with _client(_BrokenAgent(), timeout_seconds=5) as client:
        run_id = client.post("/v1/agents/atlas/run", json={"prompt": "hi"}).json()["id"]
        fetched = client.get(f"/v1/runs/{run_id}").json()

    assert fetched["status"] == "failed"
    assert fetched["error_code"] == "internal_error"
