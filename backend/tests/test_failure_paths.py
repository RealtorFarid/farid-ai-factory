"""Failure modes end-to-end: agent timeouts and mid-stream errors.

These are the branches that only execute when something is already going
wrong, so they get explicit coverage rather than relying on the happy path.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.runtime.agent import AgentRegistry, AgentSpec
from backend.runtime.config import Settings

# ---- Stub agents ---------------------------------------------------------


class _SlowStream:
    async def __aenter__(self) -> Any:
        await asyncio.sleep(10)
        raise AssertionError("should not be reached")

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _SlowAgent:
    """Never finishes within a sane timeout."""

    async def run(self, prompt: str) -> object:
        await asyncio.sleep(10)
        raise AssertionError("should not be reached")

    def run_stream(self, prompt: str) -> _SlowStream:
        return _SlowStream()


class _BrokenStream:
    async def __aenter__(self) -> Any:
        raise RuntimeError("upstream model exploded")

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


class _BrokenAgent:
    def run_stream(self, prompt: str) -> _BrokenStream:
        return _BrokenStream()


# ---- Fixtures ------------------------------------------------------------


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
    return TestClient(create_app(settings=settings, registry=registry))


def _parse_sse(raw: str) -> list[tuple[str, dict[str, Any]]]:
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


# ---- Tests ---------------------------------------------------------------


def test_run_timeout_returns_504() -> None:
    with _client(_SlowAgent()) as client:
        response = client.post("/v1/agents/atlas/run", json={"prompt": "hi"})

    assert response.status_code == 504
    error = response.json()["error"]
    assert error["code"] == "agent_timeout"
    assert "0.05" in error["message"]


def test_stream_timeout_is_reported_in_band() -> None:
    """The 200 is already committed, so a timeout must arrive as an error frame."""
    with (
        _client(_SlowAgent()) as client,
        client.stream("POST", "/v1/agents/atlas/stream", json={"prompt": "hi"}) as response,
    ):
        assert response.status_code == 200
        frames = _parse_sse(response.read().decode())

    assert [name for name, _ in frames] == ["error"]
    assert frames[0][1]["code"] == "agent_timeout"
    assert frames[0][1]["request_id"]


def test_stream_internal_error_does_not_leak_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with (
        _client(_BrokenAgent(), timeout_seconds=5) as client,
        client.stream("POST", "/v1/agents/atlas/stream", json={"prompt": "hi"}) as response,
    ):
        assert response.status_code == 200
        frames = _parse_sse(response.read().decode())

    assert [name for name, _ in frames] == ["error"]
    payload = frames[0][1]
    assert payload["code"] == "internal_error"
    assert "upstream model exploded" not in payload["message"]
